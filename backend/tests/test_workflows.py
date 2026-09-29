"""Temporal workflow logic tested with the time-skipping test server and mocked activities.

Days of SLA timers elapse in milliseconds, so escalation paths are verified exactly.
Skipped automatically if the Temporal test-server binary cannot be downloaded.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.workflows.definitions import ComplianceReminderWorkflow, ViolationEscalationWorkflow


@pytest.fixture(scope="module")
async def env() -> Any:
    try:
        environment = await WorkflowEnvironment.start_time_skipping()
    except Exception as exc:  # offline CI without the test server binary
        pytest.skip(f"temporal test server unavailable: {exc}")
    yield environment
    await environment.shutdown()


class FakeViolation:
    """In-memory stand-in for the database, driven by mocked activities."""

    def __init__(self, severity: str = "high") -> None:
        self.status = "open"
        self.severity = severity
        self.level = 0
        self.actions: list[dict[str, Any]] = []
        self.escalations: list[tuple[int, str]] = []
        self.calls: list[str] = []

    def activities(self) -> list[Any]:
        fv = self

        @activity.defn(name="load_violation_state")
        async def load(violation_id: str) -> dict[str, Any]:
            return {"exists": True, "status": fv.status, "severity": fv.severity, "escalation_level": fv.level,
                    "mine_id": "mine-1", "open_actions": [a for a in fv.actions if a["status"] != "verified"],
                    "has_actions": bool(fv.actions)}

        @activity.defn(name="escalate_violation")
        async def escalate(violation_id: str, level: int, reason: str) -> int:
            fv.level = level
            fv.escalations.append((level, reason))
            return level

        @activity.defn(name="mark_actions_overdue")
        async def overdue(violation_id: str) -> list[str]:
            marked = []
            for a in fv.actions:
                if a["status"] in ("assigned", "in_progress"):
                    a["status"] = "overdue"
                    marked.append(a["id"])
            return marked

        def noop(name: str, result: Any = None) -> Any:
            @activity.defn(name=name)
            async def _fn(*args: Any) -> Any:
                fv.calls.append(name)
                return result

            return _fn

        return [load, escalate, overdue, noop("classify_violation_ai", "high"), noop("index_violation", 1),
                noop("refresh_mine_risk", 50.0), noop("remind_verification_pending")]


async def _run_worker(env: WorkflowEnvironment, fv: FakeViolation, queue: str) -> Worker:
    return Worker(env.client, task_queue=queue, workflows=[ViolationEscalationWorkflow], activities=fv.activities())


async def test_unassigned_violation_escalates_through_levels(env: WorkflowEnvironment) -> None:
    fv = FakeViolation("high")  # 24h SLA
    queue = f"q-{uuid.uuid4().hex}"
    async with await _run_worker(env, fv, queue):
        handle = await env.client.start_workflow(
            ViolationEscalationWorkflow.run, {"violation_id": "v1"}, id=f"wf-{uuid.uuid4().hex}", task_queue=queue)
        await env.sleep(timedelta(hours=24 * 3 + 1))
        assert [lvl for lvl, _ in fv.escalations] == [1, 2, 3]
        assert "No corrective action assigned" in fv.escalations[0][1]
        assert fv.calls[:2] == ["classify_violation_ai", "index_violation"]
        fv.status = "closed"
        await handle.signal(ViolationEscalationWorkflow.closed)
        assert await handle.result() == "closed"


async def test_assignment_signal_stops_escalation_then_deadline_overdue(env: WorkflowEnvironment) -> None:
    fv = FakeViolation("medium")  # 72h SLA
    queue = f"q-{uuid.uuid4().hex}"
    async with await _run_worker(env, fv, queue):
        handle = await env.client.start_workflow(
            ViolationEscalationWorkflow.run, {"violation_id": "v2"}, id=f"wf-{uuid.uuid4().hex}", task_queue=queue)
        await env.sleep(timedelta(hours=10))
        now = await env.get_current_time()
        fv.actions.append({"id": "a1", "status": "assigned", "deadline": (now + timedelta(days=2)).isoformat()})
        fv.status = "action_assigned"
        await handle.signal(ViolationEscalationWorkflow.action_assigned, {"action_id": "a1"})
        await env.sleep(timedelta(days=1))
        assert fv.escalations == []  # assigned within SLA, deadline not reached
        assert await handle.query(ViolationEscalationWorkflow.stage) == "awaiting_completion"
        await env.sleep(timedelta(days=1, hours=2))
        assert fv.actions[0]["status"] == "overdue"
        assert fv.escalations and "missed their deadline" in fv.escalations[0][1]
        # Submission and verification close the loop.
        fv.actions[0]["status"] = "verified"
        fv.status = "closed"
        await handle.signal(ViolationEscalationWorkflow.action_verified, {"action_id": "a1", "approved": True})
        assert await handle.result() == "closed"


class FakeCompliance:
    def __init__(self, due: date) -> None:
        self.due = due
        self.status = "due"
        self.reminders: list[int] = []
        self.escalations = 0

    def activities(self) -> list[Any]:
        fc = self

        @activity.defn(name="load_compliance_state")
        async def load(item_id: str) -> dict[str, Any]:
            return {"exists": True, "status": fc.status, "due_date": fc.due.isoformat(), "frequency": "one_time",
                    "escalated": fc.escalations > 0}

        @activity.defn(name="send_compliance_reminder")
        async def remind(item_id: str, days_left: int) -> None:
            fc.reminders.append(days_left)

        @activity.defn(name="escalate_overdue_compliance")
        async def escalate(item_id: str, repeat: int) -> bool:
            fc.escalations += 1
            fc.status = "overdue"
            return True

        return [load, remind, escalate]


async def test_compliance_reminders_then_escalation(env: WorkflowEnvironment) -> None:
    start = await env.get_current_time()
    fc = FakeCompliance(due=(start + timedelta(days=10)).date())
    queue = f"q-{uuid.uuid4().hex}"
    async with Worker(env.client, task_queue=queue, workflows=[ComplianceReminderWorkflow], activities=fc.activities()):
        handle = await env.client.start_workflow(
            ComplianceReminderWorkflow.run, {"item_id": "c1"}, id=f"wf-{uuid.uuid4().hex}", task_queue=queue)
        await env.sleep(timedelta(days=12))
        assert fc.reminders == [7, 3, 1]
        assert fc.escalations == 1
        await env.sleep(timedelta(days=7, hours=1))
        assert fc.escalations == 2  # weekly re-escalation while still overdue
        fc.status = "compliant"
        await handle.signal(ComplianceReminderWorkflow.updated)
        assert await handle.result() == "complied"

