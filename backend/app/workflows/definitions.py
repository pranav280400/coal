"""Temporal workflow definitions (durable, deterministic orchestration).

1. ComplianceReminderWorkflow   — reminders before due date, escalation after (FR2)
2. ViolationEscalationWorkflow  — violation → action → deadline → verification → close (FR6)
3. FieldIngestAgentWorkflow     — OCR → summarise → detect hazards → embed → risk-score → alert
4. ReportGenerationWorkflow     — aggregate → LLM narrative → PDF/XLSX → notify (FR13)
5. DocumentDigitizationWorkflow — OCR → LLM structuring → embeddings (FR14)
6. GrievanceSLAWorkflow         — escalate a grievance each time it passes its resolution deadline
+ scheduled: ScheduledReportsWorkflow, RiskAnalyticsWorkflow, ComplianceSweepWorkflow,
  KnowledgeIndexWorkflow.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from app.workflows import activities as act

STANDARD = RetryPolicy(initial_interval=timedelta(seconds=2), backoff_coefficient=2.0,
                       maximum_interval=timedelta(minutes=2), maximum_attempts=6)
AI_RETRY = RetryPolicy(initial_interval=timedelta(seconds=10), backoff_coefficient=2.0,
                       maximum_interval=timedelta(minutes=5), maximum_attempts=4)
SHORT = timedelta(seconds=60)
LONG = timedelta(minutes=10)

SLA_HOURS = {"critical": 4, "high": 24, "medium": 72, "low": 168}
REMINDER_DAYS = (7, 3, 1)
MAX_LEVEL = 3
IST_MORNING_UTC = time(3, 30)  # 09:00 IST


async def _run(fn: Any, *args: Any, timeout: timedelta = SHORT, retry: RetryPolicy = STANDARD) -> Any:
    return await workflow.execute_activity(fn, args=list(args), start_to_close_timeout=timeout, retry_policy=retry)


async def _try(fn: Any, *args: Any, timeout: timedelta = LONG, retry: RetryPolicy = AI_RETRY) -> Any:
    """Run a best-effort step; failures are logged and the pipeline continues."""
    try:
        return await _run(fn, *args, timeout=timeout, retry=retry)
    except ActivityError as exc:
        workflow.logger.warning("step %s failed: %s", getattr(fn, "__name__", fn), exc.cause)
        return None


# ===================================================================== FR6
@workflow.defn
class ViolationEscalationWorkflow:
    def __init__(self) -> None:
        self._changed = False
        self._closed = False
        self._stage = "starting"
        self._severity: str | None = None

    @workflow.signal
    def action_assigned(self, payload: dict[str, Any]) -> None:
        self._changed = True

    @workflow.signal
    def action_submitted(self, action_id: str) -> None:
        self._changed = True

    @workflow.signal
    def action_verified(self, payload: dict[str, Any]) -> None:
        self._changed = True

    @workflow.signal
    def severity_changed(self, severity: str) -> None:
        self._severity = severity
        self._changed = True

    @workflow.signal
    def closed(self) -> None:
        self._closed = True
        self._changed = True

    @workflow.query
    def stage(self) -> str:
        return self._stage

    async def _wait(self, timeout: timedelta) -> bool:
        """True if something changed (signal) before the timeout."""
        # The flag is cleared just before state is reloaded (not here), so a signal that
        # arrives while an activity is running is never lost.
        try:
            await workflow.wait_condition(lambda: self._changed, timeout=max(timeout, timedelta(seconds=1)))
            return True
        except TimeoutError:
            return False

    @workflow.run
    async def run(self, params: dict[str, Any]) -> str:
        violation_id: str = params["violation_id"]
        level: int = int(params.get("level", 0))
        if not params.get("enriched"):
            self._stage = "ai_enrichment"
            await _try(act.classify_violation_ai, violation_id)
            await _try(act.index_violation, violation_id)
            state0 = await _run(act.load_violation_state, violation_id)
            if state0.get("mine_id"):
                await _try(act.refresh_mine_risk, state0["mine_id"], timeout=SHORT)

        while True:
            if workflow.info().is_continue_as_new_suggested():
                workflow.continue_as_new({"violation_id": violation_id, "level": level, "enriched": True})
            self._changed = False
            state = await _run(act.load_violation_state, violation_id)
            if not state["exists"] or state["status"] == "closed" or self._closed:
                break
            severity = self._severity or state["severity"]
            level = max(level, int(state["escalation_level"]))
            open_actions: list[dict[str, Any]] = state["open_actions"] or []
            now = workflow.now()

            if not open_actions:
                self._stage = "awaiting_assignment"
                if await self._wait(timedelta(hours=SLA_HOURS.get(severity, 72))):
                    continue
                level = min(level + 1, MAX_LEVEL)
                await _run(act.escalate_violation, violation_id, level,
                           f"No corrective action assigned within the {SLA_HOURS.get(severity, 72)}h SLA for "
                           f"{severity} violations")
                continue

            pending = [a for a in open_actions if a["status"] in ("assigned", "in_progress", "rejected")]
            overdue = [a for a in open_actions if a["status"] == "overdue"]
            if pending:
                self._stage = "awaiting_completion"
                nearest = min(datetime.fromisoformat(a["deadline"]) for a in pending)
                if nearest > now:
                    if await self._wait(nearest - now):
                        continue
                marked = await _run(act.mark_actions_overdue, violation_id)
                if marked:
                    level = min(level + 1, MAX_LEVEL)
                    await _run(act.escalate_violation, violation_id, level,
                               f"{len(marked)} corrective action(s) missed their deadline")
                continue
            if overdue:
                self._stage = "overdue"
                # Re-escalate daily while actions remain overdue.
                if await self._wait(timedelta(hours=24)):
                    continue
                level = min(level + 1, MAX_LEVEL)
                await _run(act.escalate_violation, violation_id, level, "Corrective actions remain overdue")
                continue
            self._stage = "awaiting_verification"
            if not await self._wait(timedelta(hours=72)):
                await _run(act.remind_verification_pending, violation_id)

        self._stage = "closed"
        state = await _run(act.load_violation_state, violation_id)
        await _try(act.index_violation, violation_id)
        if state.get("mine_id"):
            await _try(act.refresh_mine_risk, state["mine_id"], timeout=SHORT)
        return "closed"


# ===================================================================== FR2
@workflow.defn
class ComplianceReminderWorkflow:
    def __init__(self) -> None:
        self._changed = False

    @workflow.signal
    def updated(self) -> None:
        self._changed = True

    async def _wait(self, timeout: timedelta) -> bool:
        # The flag is cleared just before state is reloaded (not here), so a signal that
        # arrives while an activity is running is never lost.
        try:
            await workflow.wait_condition(lambda: self._changed, timeout=max(timeout, timedelta(seconds=1)))
            return True
        except TimeoutError:
            return False

    @workflow.run
    async def run(self, params: dict[str, Any]) -> str:
        item_id: str = params["item_id"]
        sent: list[str] = list(params.get("sent", []))
        escalations: int = int(params.get("escalations", 0))
        while True:
            if workflow.info().is_continue_as_new_suggested():
                workflow.continue_as_new({"item_id": item_id, "sent": sent[-50:], "escalations": escalations})
            self._changed = False
            state = await _run(act.load_compliance_state, item_id)
            if not state["exists"]:
                return "deleted"
            if state["status"] == "compliant" and state["frequency"] == "one_time":
                return "complied"
            due = date.fromisoformat(state["due_date"])
            now = workflow.now()
            points: list[tuple[datetime, str, int]] = []
            for days in REMINDER_DAYS:
                at = datetime.combine(due - timedelta(days=days), IST_MORNING_UTC, tzinfo=now.tzinfo)
                points.append((at, f"{due.isoformat()}:{days}", days))
            overdue_at = datetime.combine(due + timedelta(days=1), IST_MORNING_UTC, tzinfo=now.tzinfo)
            upcoming = [(at, key, d) for at, key, d in points if key not in sent and at > now]
            if state["status"] in ("compliant",):
                # Recurring item already satisfied for this period; wait for the roll-forward signal.
                await self._wait(timedelta(days=30))
                continue
            if upcoming:
                at, key, days = min(upcoming)
                if await self._wait(at - now):
                    continue
                await _run(act.send_compliance_reminder, item_id, days)
                sent.append(key)
                continue
            if now < overdue_at:
                if await self._wait(overdue_at - now):
                    continue
            escalated = await _run(act.escalate_overdue_compliance, item_id, escalations)
            if escalated:
                escalations += 1
            # Weekly re-escalation until complied / updated.
            await self._wait(timedelta(days=7))


# =============================================================== grievances
@workflow.defn
class GrievanceSLAWorkflow:
    """Sleeps until the grievance's deadline; escalates one level each time it is missed.

    Assign/resolve/reopen signal ``updated`` so the timer follows the current deadline.
    Finishes once the grievance is closed (or resolved/rejected and not reopened within 30 days).
    """

    def __init__(self) -> None:
        self._changed = False

    @workflow.signal
    def updated(self) -> None:
        self._changed = True

    async def _wait(self, timeout: timedelta) -> bool:
        try:
            await workflow.wait_condition(lambda: self._changed, timeout=max(timeout, timedelta(seconds=1)))
            return True
        except TimeoutError:
            return False

    @workflow.run
    async def run(self, params: dict[str, Any]) -> str:
        grievance_id: str = params["grievance_id"]
        while True:
            if workflow.info().is_continue_as_new_suggested():
                workflow.continue_as_new({"grievance_id": grievance_id})
            self._changed = False
            state = await _run(act.escalate_grievance_if_overdue, grievance_id)
            if not state.get("exists"):
                return "deleted"
            status = state["status"]
            if status == "closed":
                return "closed"
            if status in ("resolved", "rejected"):
                # Waiting for the raiser to confirm or reopen.
                if await self._wait(timedelta(days=30)):
                    continue
                return status
            due = datetime.fromisoformat(state["due_at"])
            await self._wait(due - workflow.now())


# ================================================================ pipeline
@workflow.defn
class FieldIngestAgentWorkflow:
    @workflow.run
    async def run(self, inspection_id: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        result["ocr_attachments"] = await _try(act.ocr_inspection_attachments, inspection_id)
        analysis = await _try(act.summarize_inspection_ai, inspection_id)
        result["ai_summary"] = bool(analysis)
        if analysis and analysis.get("hazards"):
            created = await _try(act.create_ai_violations, inspection_id, analysis["hazards"], timeout=SHORT,
                                 retry=STANDARD)
            result["ai_violations"] = len(created or [])
        result["indexed_chunks"] = await _try(act.index_inspection, inspection_id)
        mine_id = await _run(act.finish_inspection_processing, inspection_id)
        if mine_id:
            # Re-score the mine; a jump into the high band emits a risk alert event.
            result["risk_score"] = await _try(act.refresh_mine_risk, mine_id, timeout=SHORT)
        return result


@workflow.defn
class DocumentDigitizationWorkflow:
    @workflow.run
    async def run(self, document_id: str) -> dict[str, Any]:
        try:
            ocr_result = await _run(act.digitize_document, document_id, timeout=timedelta(minutes=30),
                                    retry=RetryPolicy(maximum_attempts=3, non_retryable_error_types=["ApplicationError"]))
        except ActivityError as exc:
            cause = exc.cause
            msg = cause.message if isinstance(cause, ApplicationError) else str(cause)
            await _run(act.finish_document, document_id, False, f"Digitisation failed: {msg}")
            return {"ok": False, "error": msg}
        if ocr_result.get("missing"):
            return {"ok": False, "error": "document deleted"}
        fields = await _try(act.structure_document_ai, document_id)
        chunks = await _try(act.index_document, document_id)
        error = None if chunks is not None else "Text extracted; semantic indexing will retry when the AI service is available"
        await _run(act.finish_document, document_id, True, error)
        return {"ok": True, "ocr": ocr_result, "structured": bool(fields), "chunks": chunks}


@workflow.defn
class ReportGenerationWorkflow:
    @workflow.run
    async def run(self, report_id: str) -> dict[str, Any]:
        try:
            return await _run(act.build_report, report_id, True, timeout=timedelta(minutes=15),
                              retry=RetryPolicy(maximum_attempts=3))
        except ActivityError as exc:
            await _run(act.fail_report, report_id, str(exc.cause))
            raise


# =============================================================== scheduled
@workflow.defn
class ScheduledReportsWorkflow:
    @workflow.run
    async def run(self) -> list[str]:
        ids: list[str] = await _run(act.create_scheduled_reports, None)
        for rid in ids:
            await workflow.start_child_workflow(
                ReportGenerationWorkflow.run, rid, id=f"report-generation-{rid}",
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )
        return ids


@workflow.defn
class RiskAnalyticsWorkflow:
    @workflow.run
    async def run(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        out: dict[str, Any] = {}
        if params.get("train"):
            out["training"] = await _try(act.train_risk_model, timeout=timedelta(minutes=30), retry=STANDARD)
        out["risk"] = await _run(act.recompute_all_risk, timeout=timedelta(minutes=30))
        out["anomalies"] = await _run(act.detect_anomalies, timeout=timedelta(minutes=30))
        return out


@workflow.defn
class ComplianceSweepWorkflow:
    @workflow.run
    async def run(self) -> dict[str, Any]:
        sweep = await _run(act.compliance_sweep, timeout=timedelta(minutes=10))
        started = 0
        for item_id in sweep["open_item_ids"]:
            try:
                await workflow.start_child_workflow(
                    ComplianceReminderWorkflow.run, {"item_id": item_id}, id=f"compliance-reminder-{item_id}",
                    parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                )
                started += 1
            except Exception:  # already running (WorkflowAlreadyStartedError) — expected for most items
                pass
        pending = await _run(act.reconcile_pending)
        for doc_id in pending["documents"]:
            try:
                await workflow.start_child_workflow(
                    DocumentDigitizationWorkflow.run, doc_id, id=f"document-digitize-{doc_id}-sweep-{workflow.now():%Y%m%d}",
                    parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                )
            except Exception:
                pass
        for report_id in pending["reports"]:
            try:
                await workflow.start_child_workflow(
                    ReportGenerationWorkflow.run, report_id, id=f"report-generation-{report_id}",
                    parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                )
            except Exception:
                pass
        grievance_timers = 0
        for grievance_id in pending.get("grievances", []):
            try:
                await workflow.start_child_workflow(
                    GrievanceSLAWorkflow.run, {"grievance_id": grievance_id}, id=f"grievance-sla-{grievance_id}",
                    parent_close_policy=workflow.ParentClosePolicy.ABANDON,
                )
                grievance_timers += 1
            except Exception:  # already running
                pass
        return {"newly_overdue": sweep["newly_overdue"], "reminder_workflows_started": started,
                "grievance_timers_started": grievance_timers,
                "documents": pending["documents"], "reports": pending["reports"]}


@workflow.defn
class KnowledgeIndexWorkflow:
    @workflow.run
    async def run(self, force: bool = False) -> int:
        return await _run(act.index_regulations, force, timeout=timedelta(minutes=60), retry=AI_RETRY)


ALL_WORKFLOWS = [
    ViolationEscalationWorkflow, ComplianceReminderWorkflow, FieldIngestAgentWorkflow,
    DocumentDigitizationWorkflow, ReportGenerationWorkflow, ScheduledReportsWorkflow,
    RiskAnalyticsWorkflow, ComplianceSweepWorkflow, KnowledgeIndexWorkflow, GrievanceSLAWorkflow,
]
