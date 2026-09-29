"""Database-backed analytics: risk scoring (FR7), anomaly detection (FR8), model lifecycle."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import anomaly as anomaly_mod
from app.ai import risk
from app.core import storage
from app.core.config import get_settings
from app.core.metrics import RISK_SCORE
from app.models import (
    Anomaly,
    AttendanceRecord,
    ComplianceItem,
    Contractor,
    CorrectiveAction,
    Inspection,
    Mine,
    MLModel,
    RiskScore,
    Violation,
)
from app.models.enums import AnomalyKind, AnomalyStatus, Severity
from app.services.access import Principal, scope_mines
from app.services.events import record_event

logger = logging.getLogger(__name__)

_model_cache: dict[str, Any] = {}


async def load_histories(
    session: AsyncSession, *, by: str = "mine", since_days: int = 800, only: uuid.UUID | None = None
) -> dict[uuid.UUID, risk.EntityHistory]:
    """Load compact histories for every mine (or contractor) in one pass per table."""
    since = datetime.now(UTC) - timedelta(days=since_days)
    key_col = Violation.mine_id if by == "mine" else Violation.contractor_id
    histories: dict[uuid.UUID, risk.EntityHistory] = defaultdict(risk.EntityHistory)
    vstmt = select(key_col, Violation.id, Violation.occurred_at, Violation.severity, Violation.category,
                   Violation.closed_at, Violation.escalation_level).where(Violation.occurred_at >= since,
                                                                          key_col.is_not(None))
    if only:
        vstmt = vstmt.where(key_col == only)
    rows = await session.execute(vstmt)
    violation_owner: dict[uuid.UUID, uuid.UUID] = {}
    for owner, vid, occurred, sev, cat, closed, esc in rows.all():
        histories[owner].violations.append(risk.ViolationRow(occurred, sev.value, cat.value, closed, esc or 0))
        violation_owner[vid] = owner
    arows = await session.execute(
        select(CorrectiveAction.violation_id, CorrectiveAction.deadline, CorrectiveAction.submitted_at,
               CorrectiveAction.status).where(CorrectiveAction.created_at >= since)
    )
    for vid, deadline, submitted, status in arows.all():
        owner = violation_owner.get(vid)
        if owner:
            histories[owner].actions.append(risk.ActionRow(deadline, submitted, status.value))
    if by == "mine":
        cstmt = select(ComplianceItem.mine_id, ComplianceItem.due_date, ComplianceItem.last_completed_at,
                       ComplianceItem.status)
        istmt = select(Inspection.mine_id, Inspection.inspected_at, Inspection.outcome).where(
            Inspection.inspected_at >= since
        )
        if only:
            cstmt = cstmt.where(ComplianceItem.mine_id == only)
            istmt = istmt.where(Inspection.mine_id == only)
        for mine_id, due, done, status in (await session.execute(cstmt)).all():
            histories[mine_id].compliance.append(risk.ComplianceRow(due, done, status.value))
        for mine_id, at, outcome in (await session.execute(istmt)).all():
            histories[mine_id].inspections.append(risk.InspectionRow(at, outcome.value))
    return histories


async def recompute_mine_risk(session: AsyncSession, mine_id: uuid.UUID) -> float | None:
    """Incremental re-score of one mine (after a new inspection/violation)."""
    s = get_settings()
    mine = await session.get(Mine, mine_id)
    if mine is None:
        return None
    histories = await load_histories(session, by="mine", only=mine_id)
    feats = risk.compute_features(histories.get(mine_id, risk.EntityHistory()), datetime.now(UTC))
    model = await active_model(session)
    score, explanation = model.score(feats) if model else risk.expert_score(feats)
    old = mine.risk_score
    mine.risk_score = score
    mine.risk_updated_at = datetime.now(UTC)
    session.add(RiskScore(entity_type="mine", entity_id=mine_id, score=score, band=risk.band(score),
                          factors=explanation, model_version=model.version if model else "expert-v1"))
    RISK_SCORE.labels(mine.code).set(score)
    if score >= s.high_risk_threshold and (old is None or old < s.high_risk_threshold):
        record_event(
            session, "risk.high_detected", entity_type="mine", entity_id=mine_id, actor=None,
            mine_id=mine_id, subsidiary_id=mine.subsidiary_id,
            data={"score": score, "previous": old, "band": risk.band(score),
                  "drivers": explanation["drivers"], "mine_name": mine.name},
        )
    await session.commit()
    return score


async def active_model(session: AsyncSession) -> risk.TrainedModel | None:
    row = (
        await session.execute(
            select(MLModel).where(MLModel.name == "mine_risk", MLModel.is_active.is_(True))
            .order_by(MLModel.created_at.desc()).limit(1)
        )
    ).scalars().first()
    if row is None:
        return None
    cached = _model_cache.get("mine_risk")
    if cached and cached.version == row.version:
        return cached
    try:
        blob = await storage.get_object(row.storage_key)
    except Exception as exc:
        logger.warning("could not load model %s: %s", row.version, exc)
        return None
    model = risk.TrainedModel.loads(blob, row.version, row.metrics, row.trained_samples)
    _model_cache["mine_risk"] = model
    return model


async def train_risk_model(session: AsyncSession) -> dict[str, Any]:
    histories = await load_histories(session, by="mine")
    x, y = risk.build_training_set(list(histories.values()))
    model = risk.train(x, y)
    if model is None:
        return {"trained": False, "samples": int(len(y)), "positives": int(y.sum()) if len(y) else 0,
                "reason": "insufficient labelled history; expert baseline remains in use"}
    key = f"models/mine_risk/{model.version}.joblib"
    await storage.put_object(key, model.dumps(), "application/octet-stream")
    activate = model.metrics["cv_roc_auc"] >= risk.MIN_ACTIVATION_AUC
    if activate:
        await session.execute(update(MLModel).where(MLModel.name == "mine_risk").values(is_active=False))
    session.add(
        MLModel(name="mine_risk", version=model.version, storage_key=key, metrics=model.metrics,
                feature_names=risk.FEATURES, is_active=activate, trained_samples=model.samples)
    )
    await session.commit()
    if activate:
        _model_cache["mine_risk"] = model
    return {"trained": True, "activated": activate, "version": model.version, "metrics": model.metrics,
            "samples": model.samples,
            "note": None if activate else f"cv_roc_auc below {risk.MIN_ACTIVATION_AUC}; expert baseline kept"}


async def recompute_risk(session: AsyncSession) -> dict[str, Any]:
    """Score every mine and contractor; persist history; emit events for band escalations."""
    s = get_settings()
    now = datetime.now(UTC)
    model = await active_model(session)
    mines = {m.id: m for m in (await session.execute(select(Mine))).scalars().unique().all()}
    histories = await load_histories(session, by="mine")
    raised: list[str] = []
    for mine_id, mine in mines.items():
        feats = risk.compute_features(histories.get(mine_id, risk.EntityHistory()), now)
        if model:
            score, explanation = model.score(feats)
            version = model.version
        else:
            score, explanation = risk.expert_score(feats)
            version = "expert-v1"
        old = mine.risk_score
        mine.risk_score = score
        mine.risk_updated_at = now
        session.add(RiskScore(entity_type="mine", entity_id=mine_id, score=score, band=risk.band(score),
                              factors=explanation, model_version=version))
        RISK_SCORE.labels(mine.code).set(score)
        if score >= s.high_risk_threshold and (old is None or old < s.high_risk_threshold):
            record_event(
                session, "risk.high_detected", entity_type="mine", entity_id=mine_id, actor=None,
                mine_id=mine_id, subsidiary_id=mine.subsidiary_id,
                data={"score": score, "previous": old, "band": risk.band(score),
                      "drivers": explanation["drivers"], "mine_name": mine.name},
            )
            raised.append(mine.name)

    c_histories = await load_histories(session, by="contractor")
    contractors = (await session.execute(select(Contractor))).scalars().unique().all()
    for c in contractors:
        feats = risk.compute_features(c_histories.get(c.id, risk.EntityHistory()), now)
        score, explanation = risk.expert_score(feats)
        c.risk_score = score
        c.compliance_score = risk.contractor_compliance_score(feats)
        session.add(RiskScore(entity_type="contractor", entity_id=c.id, score=score, band=risk.band(score),
                              factors=explanation, model_version="expert-v1"))
    await session.commit()
    return {"mines": len(mines), "contractors": len(contractors), "model": model.version if model else "expert-v1",
            "newly_high_risk": raised}


async def _store_findings(session: AsyncSession, mine: Mine, findings: list[anomaly_mod.Finding]) -> int:
    created = 0
    for f in findings:
        exists = (
            await session.execute(
                select(Anomaly.id).where(Anomaly.fingerprint == f.fingerprint, Anomaly.status != AnomalyStatus.RESOLVED)
            )
        ).first()
        if exists:
            continue
        a = Anomaly(mine_id=mine.id, kind=AnomalyKind(f.kind), fingerprint=f.fingerprint, title=f.title,
                    description=f.description, metric=f.metric, score=f.score)
        session.add(a)
        await session.flush()
        record_event(
            session, "anomaly.detected", entity_type="anomaly", entity_id=a.id, actor=None,
            mine_id=mine.id, subsidiary_id=mine.subsidiary_id,
            data={"kind": f.kind, "title": f.title, "description": f.description, "score": f.score},
        )
        created += 1
    return created


async def detect_recurring_for_mine(session: AsyncSession, mine_id: uuid.UUID) -> int:
    s = get_settings()
    mine = await session.get(Mine, mine_id)
    if mine is None:
        return 0
    now = datetime.now(UTC)
    since = now - timedelta(days=s.recurring_violation_window_days + 200)
    rows = (
        await session.execute(
            select(Violation.occurred_at, Violation.category).where(
                Violation.mine_id == mine_id, Violation.occurred_at >= since
            )
        )
    ).all()
    findings = anomaly_mod.recurring_violations(
        [(t, c.value) for t, c in rows], now=now, mine_label=mine.name, mine_id=str(mine.id),
        threshold=s.recurring_violation_threshold, window_days=s.recurring_violation_window_days,
    )
    return await _store_findings(session, mine, findings)


async def detect_all(session: AsyncSession) -> dict[str, int]:
    now = datetime.now(UTC)
    today = now.date()
    since = now - timedelta(days=90)
    mines = (await session.execute(select(Mine).where(Mine.is_active.is_(True)))).scalars().unique().all()
    daily: dict[uuid.UUID, dict[date, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0, 0.0]))
    for mine_id, day, n in (
        await session.execute(
            select(Inspection.mine_id, func.date(Inspection.inspected_at), func.count())
            .where(Inspection.inspected_at >= since).group_by(Inspection.mine_id, func.date(Inspection.inspected_at))
        )
    ).all():
        daily[mine_id][day][0] = n
    for mine_id, day, n, serious in (
        await session.execute(
            select(
                Violation.mine_id, func.date(Violation.occurred_at), func.count(),
                func.count().filter(Violation.severity.in_([Severity.HIGH, Severity.CRITICAL])),
            ).where(Violation.occurred_at >= since).group_by(Violation.mine_id, func.date(Violation.occurred_at))
        )
    ).all():
        daily[mine_id][day][1] = n
        daily[mine_id][day][2] = serious
    for mine_id, day, n in (
        await session.execute(
            select(AttendanceRecord.mine_id, func.date(AttendanceRecord.check_in_at), func.count())
            .where(AttendanceRecord.check_in_at >= since)
            .group_by(AttendanceRecord.mine_id, func.date(AttendanceRecord.check_in_at))
        )
    ).all():
        daily[mine_id][day][3] = n
    counts = {"recurring": 0, "operational": 0, "attendance": 0}
    for mine in mines:
        counts["recurring"] += await detect_recurring_for_mine(session, mine.id)
        series = daily.get(mine.id, {})
        full = {today - timedelta(days=i): tuple(series.get(today - timedelta(days=i), [0.0, 0.0, 0.0, 0.0]))
                for i in range(1, 91)}
        if sum(v[0] + v[1] + v[3] for v in full.values()) > 0:
            counts["operational"] += await _store_findings(
                session, mine, anomaly_mod.operational_outliers(full, mine_label=mine.name, mine_id=str(mine.id))
            )
        att = {d: int(v[3]) for d, v in full.items()}
        counts["attendance"] += await _store_findings(
            session, mine, anomaly_mod.attendance_drop(att, today=today, mine_label=mine.name, mine_id=str(mine.id))
        )
    await session.commit()
    return counts


async def risk_ranking(session: AsyncSession, principal: Principal, entity_type: str, limit: int) -> list[dict[str, Any]]:
    latest = (
        select(RiskScore.entity_id, func.max(RiskScore.computed_at).label("ts"))
        .where(RiskScore.entity_type == entity_type).group_by(RiskScore.entity_id).subquery()
    )
    joined = select(RiskScore).join(
        latest, (RiskScore.entity_id == latest.c.entity_id) & (RiskScore.computed_at == latest.c.ts)
    ).where(RiskScore.entity_type == entity_type)
    scores = {r.entity_id: r for r in (await session.execute(joined)).scalars().all()}
    out: list[dict[str, Any]] = []
    if entity_type == "mine":
        mines = (await session.execute(scope_mines(select(Mine), principal, Mine.id))).scalars().unique().all()
        for m in mines:
            r = scores.get(m.id)
            if r:
                out.append({"entity_type": "mine", "entity_id": m.id, "name": m.name, "code": m.code,
                            "score": r.score, "band": r.band, "factors": r.factors, "computed_at": r.computed_at})
    else:
        from app.services.contractors import base_query as contractor_query

        contractors = (await session.execute(contractor_query(principal))).scalars().unique().all()
        for c in contractors:
            r = scores.get(c.id)
            if r:
                out.append({"entity_type": "contractor", "entity_id": c.id, "name": c.name, "code": c.registration_no,
                            "score": r.score, "band": r.band, "factors": r.factors, "computed_at": r.computed_at})
    out.sort(key=lambda e: e["score"], reverse=True)
    return out[:limit]


async def risk_history(session: AsyncSession, entity_id: uuid.UUID, days: int = 180) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        await session.execute(
            select(RiskScore.computed_at, RiskScore.score).where(RiskScore.entity_id == entity_id,
                                                                 RiskScore.computed_at >= since)
            .order_by(RiskScore.computed_at)
        )
    ).all()
    return [{"at": at.isoformat(), "score": score} for at, score in rows]


async def category_breakdown(session: AsyncSession, principal: Principal, days: int = 365) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    stmt = scope_mines(
        select(Violation.category, Violation.severity, func.count())
        .where(Violation.occurred_at >= since).group_by(Violation.category, Violation.severity),
        principal, Violation.mine_id,
    )
    table: dict[str, dict[str, int]] = defaultdict(lambda: {s.value: 0 for s in Severity})
    for cat, sev, n in (await session.execute(stmt)).all():
        table[cat.value][sev.value] = int(n)
    return [{"category": k, **v, "total": sum(v.values())} for k, v in sorted(table.items())]
