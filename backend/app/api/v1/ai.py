"""AI assistant (RAG chat, multilingual), semantic search and summarisation."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.ai import assistant, llm, ocr, rag, vectorstore
from app.ai import attachments as attach_store
from app.api.deps import DB, CurrentPrincipal
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.errors import InvalidState, NotFound, ServiceUnavailable
from app.models import ChatMessage, ChatSession, User
from app.schemas.field import SimilarItem
from app.schemas.governance import ChatMessageOut, ChatRequest, ChatSessionOut, SemanticSearchRequest
from app.services import dashboard as dashboard_svc
from app.services import inspections as inspection_svc
from app.services import media as media_svc
from app.services.access import Perm, visible_mine_ids

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)


def _sse(event: str, data: Any) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


def _live_data(summary: dict[str, Any]) -> str:
    k = summary["kpis"]
    lines = [
        f"Mines: {k['total_mines']}; statutory items: {k['compliance_items']} ({k['compliance_rate']}% on track)",
        f"Open violations: {k['open_violations']} ({k['critical_violations']} critical); open anomalies: {k['open_anomalies']}",
        f"Inspections: {k['inspections']} total, {k['inspections_this_month']} this month",
        f"Active contractors: {k['active_contractors']} ({k['verified_contractors']} verified)",
    ]
    if summary.get("upcoming_deadlines"):
        lines.append("Nearest deadlines: " + "; ".join(
            f"{d['title']} @ {d['mine_name']} due {d['due_date']} ({d['status']})" for d in summary["upcoming_deadlines"][:5]
        ))
    if summary.get("high_risk_mines"):
        lines.append("Highest-risk mines: " + ", ".join(
            f"{m['name']} ({m['risk_score']:.0f})" for m in summary["high_risk_mines"] if m.get("risk_score") is not None
        ))
    return "\n".join(lines)


def _platform_policy() -> str:
    """The platform's own configured thresholds.

    Questions like "how long do I have to close a critical violation?" are answered by
    this deployment's configuration, not by statute. Without those values in the prompt
    the model has nothing to ground on and will invent a plausible-sounding section
    number, so they are stated explicitly.
    """
    s = get_settings()
    return "\n".join([
        "Corrective-action SLA by severity (configured in this deployment): "
        f"critical {s.sla_critical_hours}h, high {s.sla_high_hours}h, "
        f"medium {s.sla_medium_hours}h, low {s.sla_low_hours}h.",
        f"Violations escalate up to level {s.max_escalation_level} when an SLA is breached.",
        "Grievance resolution deadlines by priority: critical 24h, high 72h, medium 7 days, low 15 days; "
        "missed deadlines escalate, and the person who raised it confirms before closure.",
        "Environment readings above the legal limit (NAAQS 2009, Noise Rules 2000, coal-mine effluent "
        "standards) open an environment violation automatically.",
        "Compliance reminders are sent "
        f"{', '.join(str(d) for d in s.compliance_reminder_days)} days before the due date.",
        f"A violation pattern is flagged as recurring at {s.recurring_violation_threshold} or more "
        f"of the same type at one mine within {s.recurring_violation_window_days} days.",
        f"A mine is treated as high-risk at a risk score of {s.high_risk_threshold:.0f} or above.",
        f"Field reports are geofence-verified within {s.geofence_radius_km:.0f} km of the mine.",
    ])


async def _extra_live(session: Any, principal: Any) -> str:
    """Grievance and environment figures for the user's scope (best effort)."""
    from app.services import grievances as grievance_svc
    from app.services import operations as ops_svc

    lines = []
    try:
        g = await grievance_svc.summary(session, principal, None)
        lines.append(f"Grievances: {g['open']} open, {g['overdue']} overdue")
    except Exception as exc:  # noqa: BLE001 - optional context
        logger.debug("grievance context skipped: %s", exc)
    try:
        e = await ops_svc.environment_summary(session, principal, None)
        lines.append(f"Environment readings (30 days): {e['readings_30d']}, above limit: {e['exceedances_30d']}")
    except Exception as exc:  # noqa: BLE001
        logger.debug("environment context skipped: %s", exc)
    return "\n".join(lines)


_PING = b": keep-alive\n\n"
FIRST_TOKEN_TIMEOUT_S = 150


def _assistant_policy() -> str:
    """App rules the assistant must know, kept short: every token costs time on a CPU model."""
    s = get_settings()
    return (
        f"Fix deadlines by severity: critical {s.sla_critical_hours}h, high {s.sla_high_hours}h, "
        f"medium {s.sla_medium_hours}h, low {s.sla_low_hours}h; missed ones escalate mine -> subsidiary -> HQ. "
        f"Compliance reminders {', '.join(str(d) for d in s.compliance_reminder_days)} days before due. "
        "Grievances: critical 24h, high 72h, medium 7d, low 15d. "
        "Readings above legal limits open a violation automatically."
    )


def _assistant_live(summary: dict[str, Any], extra: str) -> str:
    k = summary["kpis"]
    return (
        f"{k['total_mines']} mines; {k['open_violations']} open violations ({k['critical_violations']} critical); "
        f"compliance {k['compliance_rate']}% on track; {k['inspections_this_month']} inspections this month."
        + (f" {extra.replace(chr(10), '; ')}." if extra else "")
    )


async def warm_assistant() -> None:
    """Prime the model with the assistant's fixed instructions so the first real question reuses them."""
    await llm.warm_up([
        {"role": "system", "content": assistant.SYSTEM.format(policy=_assistant_policy())},
        {"role": "user", "content": "Reply with OK."},
    ])


@router.get("/status")
async def assistant_status(principal: CurrentPrincipal) -> dict[str, bool]:
    """Whether the AI gateway is reachable (drives the "AI assistant is ready" indicator)."""
    principal.require(Perm.AI_USE)
    return {"ready": await llm.health()}


@router.post("/attachments")
async def upload_attachment(principal: CurrentPrincipal, file: UploadFile = File(...)) -> dict[str, Any]:
    """Attach a PDF, image or text file to the conversation; its text is read once and kept for a day."""
    principal.require(Perm.AI_USE)
    data, ctype, _ext, filename = await media_svc.read_upload(file, media_svc.DOCUMENT_TYPES)
    try:
        result = await ocr.extract_text(data, ctype)
    except ocr.OCRUnavailable as exc:
        raise ServiceUnavailable("Text recognition is not available for scanned files on this server") from exc
    except ValueError as exc:
        raise InvalidState(str(exc)) from exc
    if len(result.text.strip()) < 20:
        raise InvalidState("No readable text was found in this file")
    return await attach_store.save(str(principal.id), filename=filename, content_type=ctype,
                                   pages=result.pages, text=result.text, method=result.method)


@router.post("/chat")
async def chat(body: ChatRequest, session: DB, principal: CurrentPrincipal) -> StreamingResponse:
    principal.require(Perm.AI_USE)
    s = get_settings()
    if body.session_id:
        chat_session = await session.get(ChatSession, body.session_id)
        if chat_session is None or chat_session.user_id != principal.id:
            raise NotFound("Chat session not found")
    else:
        chat_session = ChatSession(user_id=principal.id, title=body.message[:80], language=body.language or "auto")
        session.add(chat_session)
        await session.flush()
    history_rows = (
        await session.execute(
            select(ChatMessage).where(ChatMessage.session_id == chat_session.id)
            .order_by(ChatMessage.created_at.desc()).limit(8)
        )
    ).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]
    files = await attach_store.load(str(principal.id), body.attachment_ids)
    shown = body.message if not files else (
        body.message + "\n\n" + "\n".join(f"📎 {f['filename']}" for f in files))
    session.add(ChatMessage(session_id=chat_session.id, role="user", content=shown))
    user = await session.get(User, principal.id)
    scope = await visible_mine_ids(session, principal)
    scope_ids = [str(m) for m in scope] if scope is not None else None
    summary = await dashboard_svc.get_summary(session, principal)
    extra = await _extra_live(session, principal)
    await session.commit()
    session_id = chat_session.id
    first_name = (user.full_name if user else principal.full_name).split()[0]
    role_label = (user.designation if user and user.designation else principal.role.value.replace("_", " "))
    mine_name = user.mine.name if user and user.mine else None
    await session.close()

    hindi = assistant.wants_hindi(body.message, body.language)

    async def events() -> AsyncIterator[bytes]:
        answer: list[str] = []
        cites: list[dict[str, Any]] = []
        saved = False

        async def save() -> None:
            nonlocal saved
            text = "".join(answer).strip()
            if saved or not text:
                return
            saved = True
            async with session_scope() as db:
                db.add(ChatMessage(session_id=session_id, role="assistant", content=text, citations=cites))

        try:
            # Acknowledge straight away so the UI can show progress before any work is done.
            yield _sse("meta", {"session_id": str(session_id)})
            yield _sse("status", {"stage": "thinking"})

            # Questions about an attached file always go to the model with that file.
            quick = None if files else assistant.instant_answer(
                body.message, history, hindi=hindi, first_name=first_name, settings=s, live=summary)
            if quick:
                for piece in re.findall(r"\S+\s*|\s+", quick.text):
                    answer.append(piece)
                    yield _sse("token", {"t": piece})
                    await asyncio.sleep(0.008)
                await save()
                yield _sse("suggestions", {"items": quick.suggestions})
                yield _sse("done", {"session_id": str(session_id)})
                return

            topic = assistant.resolve_topic(body.message, history)
            yield _sse("status", {"stage": "searching"})
            hits = await rag.retrieve(assistant.retrieval_query(body.message, history), scope_ids, s.rag_top_k)
            if files:
                hits = hits[:1]  # the attachment is the main source; keep the prompt short
            cites = rag.citations(hits)
            for f in files:
                cites.append({"index": len(cites) + 1, "source_type": "attachment", "source_id": f["id"],
                              "title": f["filename"], "score": 1.0, "snippet": f["text"][:240]})
            file_parts = [(f["filename"], attach_store.excerpt(body.message, f["text"],
                                                               attach_store.EXCERPT_BUDGET // len(files)))
                          for f in files]
            if cites:
                yield _sse("citations", {"citations": cites})
            yield _sse("status", {"stage": "writing"})

            messages = assistant.build_messages(
                question=body.message, hits=hits, history=history, name=first_name, role=role_label,
                mine=mine_name, policy=_assistant_policy(), live=_assistant_live(summary, extra), hindi=hindi,
                files=file_parts,
            )
            queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

            async def produce() -> None:
                try:
                    async for tok in llm.chat_stream(messages, operation="assistant", max_tokens=380):
                        await queue.put(("tok", tok))
                    await queue.put(("end", None))
                except Exception as exc:  # noqa: BLE001 - surfaced to the consumer below
                    await queue.put(("err", exc))

            producer = asyncio.create_task(produce())
            splitter = assistant.FollowUpSplitter()
            started = asyncio.get_running_loop().time()
            got_token = False
            failure: Exception | None = None
            try:
                while True:
                    try:
                        kind, val = await asyncio.wait_for(queue.get(), timeout=8)
                    except TimeoutError:
                        # Heartbeat: keeps proxies from closing the stream while the model is thinking.
                        yield _PING
                        if not got_token and asyncio.get_running_loop().time() - started > FIRST_TOKEN_TIMEOUT_S:
                            failure = TimeoutError("no response from the model")
                            break
                        continue
                    if kind == "tok":
                        got_token = True
                        out = splitter.feed(val)
                        if out:
                            answer.append(out)
                            yield _sse("token", {"t": out})
                    elif kind == "err":
                        failure = val
                        break
                    else:
                        break
            finally:
                producer.cancel()
            rest = splitter.flush()
            if rest:
                answer.append(rest)
                yield _sse("token", {"t": rest})

            if failure is not None and not "".join(answer).strip():
                logger.warning("assistant model failed: %s", failure)
                if hits:
                    lead = ("मैं अभी पूरा उत्तर नहीं बना सका। इन रिकॉर्ड में आपकी बात से जुड़ी जानकारी है:" if hindi else
                            "I couldn't finish a full answer just now, but these records look relevant:")
                    fallback = lead + "\n\n" + "\n".join(f"- **{c['title']}** [{c['index']}]" for c in cites[:4])
                else:
                    fallback = ("AI सेवा अभी व्यस्त है। कृपया थोड़ी देर में फिर पूछें।" if hindi else
                                "The AI service is busy right now. Please ask again in a moment.")
                answer.append(fallback)
                yield _sse("token", {"t": fallback})
                await save()
                yield _sse("error", {"detail": "The answer was cut short.", "retry": True})
                yield _sse("done", {"session_id": str(session_id)})
                return

            await save()
            follow = splitter.follow_ups() or assistant.suggestions_for(topic, hindi)
            yield _sse("suggestions", {"items": follow})
            yield _sse("done", {"session_id": str(session_id)})
        except llm.LLMUnavailable:
            yield _sse("error", {"detail": "The AI assistant is temporarily unavailable. Please try again shortly.", "retry": True})
        except Exception:
            logger.exception("assistant stream failed")
            yield _sse("error", {"detail": "The assistant could not complete this answer.", "retry": True})
        finally:
            # Keep whatever was written even if the browser disconnected mid-answer.
            if not saved and "".join(answer).strip():
                await asyncio.shield(save())

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/sessions", response_model=list[ChatSessionOut])
async def sessions(session: DB, principal: CurrentPrincipal) -> list[ChatSessionOut]:
    rows = (
        await session.execute(
            select(ChatSession).where(ChatSession.user_id == principal.id).order_by(ChatSession.updated_at.desc()).limit(50)
        )
    ).scalars().all()
    return [ChatSessionOut.model_validate(r) for r in rows]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def session_messages(session_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> list[ChatMessageOut]:
    chat_session = await session.get(ChatSession, session_id)
    if chat_session is None or chat_session.user_id != principal.id:
        raise NotFound("Chat session not found")
    rows = (
        await session.execute(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at))
    ).scalars().all()
    return [ChatMessageOut.model_validate(r) for r in rows]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: uuid.UUID, session: DB, principal: CurrentPrincipal) -> None:
    chat_session = await session.get(ChatSession, session_id)
    if chat_session is None or chat_session.user_id != principal.id:
        raise NotFound("Chat session not found")
    await session.delete(chat_session)
    await session.commit()


@router.post("/search", response_model=list[SimilarItem])
async def semantic_search(body: SemanticSearchRequest, session: DB, principal: CurrentPrincipal) -> list[SimilarItem]:
    principal.require(Perm.AI_USE)
    scope = await visible_mine_ids(session, principal)
    try:
        hits = await vectorstore.search(
            body.query, visible_mine_ids=[str(m) for m in scope] if scope is not None else None,
            source_types=body.source_types, limit=body.limit, score_threshold=0.2,
        )
    except llm.LLMUnavailable:
        raise
    except Exception as exc:
        raise ServiceUnavailable("Semantic search is currently unavailable") from exc
    return [SimilarItem(source_type=h["source_type"], source_id=h["source_id"], title=h["title"],
                        snippet=h["text"][:400], score=round(h["score"], 3), mine_id=h["mine_id"]) for h in hits]


class SummaryOut(BaseModel):
    summary: str
    key_findings: list[str] = []
    hazards: list[dict[str, Any]] = []
    recommended_actions: list[str] = []
    overall_outcome: str | None = None


@router.post("/inspections/{inspection_id}/summarize", response_model=SummaryOut)
async def summarize_inspection(
    inspection_id: uuid.UUID, session: DB, principal: CurrentPrincipal, language: str = "en"
) -> SummaryOut:
    principal.require(Perm.AI_USE)
    insp = await inspection_svc.get_inspection(session, principal, inspection_id)
    media = await media_svc.list_media(session, "inspection", insp.id)
    data = await rag.summarize_inspection(
        {
            "mine": insp.mine.name, "type": insp.inspection_type.value, "title": insp.title,
            "date": insp.inspected_at.isoformat(), "notes": insp.notes, "checklist": insp.checklist,
            "geo_verified": insp.geo_verified, "photo_evidence_count": len(media),
            "ocr_text_from_attachments": [m.ocr_text[:1500] for m in media if m.ocr_text],
        },
        language,
    )
    out = SummaryOut(
        summary=str(data.get("summary", "")),
        key_findings=[str(x) for x in data.get("key_findings", [])],
        hazards=[h for h in data.get("hazards", []) if isinstance(h, dict)],
        recommended_actions=[str(x) for x in data.get("recommended_actions", [])],
        overall_outcome=data.get("overall_outcome"),
    )
    if language == "en":
        insp.ai_summary = out.summary
        insp.ai_findings = out.model_dump()
        await session.commit()
    return out


class AIStatus(BaseModel):
    llm_gateway: bool
    vector_store: bool
    chat_model: str
    embedding_model: str


@router.get("/status", response_model=AIStatus)
async def ai_status(principal: CurrentPrincipal) -> AIStatus:
    s = get_settings()
    return AIStatus(llm_gateway=await llm.health(), vector_store=await vectorstore.health(),
                    chat_model=s.llm_chat_model, embedding_model=s.llm_embedding_model)
