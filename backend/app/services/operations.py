"""Production returns and environmental monitoring.

* Production: one monthly return per mine (target, produced, despatched, overburden).
  A sharp month-on-month drop or despatch far above production is flagged as an
  operational anomaly for management.
* Environment: individual air / noise / effluent readings, each checked against its
  statutory limit when recorded. A reading above the limit opens an environment
  violation automatically (detected_by = system), which then follows the normal
  violation → corrective action → escalation workflow.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.models import Anomaly, EnvironmentReading, Mine, ProductionRecord, Violation
from app.models.base import snapshot
from app.models.enums import (
    AnomalyKind,
    AnomalyStatus,
    ComplianceCategory,
    DetectedBy,
    EnvParameter,
    Severity,
    ViolationKind,
    ViolationStatus,
)
from app.schemas.operations import EnvReadingCreate, ProductionUpsert
from app.services.access import Perm, Principal, assert_mine_access, scope_mines
from app.services.compliance import add_months
from app.services.events import record_event
from app.services.violations import V_FIELDS, escalation_workflow_id


# ==================================================================== limits
@dataclass(frozen=True, slots=True)
class Limit:
    label: str
    unit: str
    group: str
    limit_min: float | None
    limit_max: float | None
    standard: str


_NAAQS = "NAAQS 2009 (CPCB), 24-hour average"
_NOISE = "Noise Pollution (Regulation & Control) Rules 2000 — industrial area"
_EFFLUENT = "EP Rules 1986, coal mine effluent standards (G.S.R. 742(E))"

LIMITS: dict[EnvParameter, Limit] = {
    EnvParameter.PM10: Limit("PM10", "µg/m³", "air", None, 100, _NAAQS),
    EnvParameter.PM2_5: Limit("PM2.5", "µg/m³", "air", None, 60, _NAAQS),
    EnvParameter.SO2: Limit("SO₂", "µg/m³", "air", None, 80, _NAAQS),
    EnvParameter.NO2: Limit("NO₂", "µg/m³", "air", None, 80, _NAAQS),
    EnvParameter.NOISE_DAY: Limit("Noise (day)", "dB(A)", "noise", None, 75, _NOISE),
    EnvParameter.NOISE_NIGHT: Limit("Noise (night)", "dB(A)", "noise", None, 70, _NOISE),
    EnvParameter.WATER_PH: Limit("Effluent pH", "pH", "water", 5.5, 9.0, _EFFLUENT),
    EnvParameter.WATER_TSS: Limit("Suspended solids (TSS)", "mg/L", "water", None, 100, _EFFLUENT),
    EnvParameter.WATER_OIL_GREASE: Limit("Oil & grease", "mg/L", "water", None, 10, _EFFLUENT),
    EnvParameter.WATER_COD: Limit("COD", "mg/L", "water", None, 250, _EFFLUENT),
}

R_FIELDS = ("parameter", "value", "unit", "limit_min", "limit_max", "exceeded", "station", "sampled_at", "source")
P_FIELDS = ("period", "target_t", "produced_t", "dispatched_t", "overburden_bcm", "closing_stock_t")


def limits() -> list[dict[str, Any]]:
    return [{"parameter": p, **{k: getattr(lim, k) for k in Limit.__slots__}} for p, lim in LIMITS.items()]


def is_exceeded(parameter: EnvParameter, value: float) -> bool:
    lim = LIMITS[parameter]
    return (lim.limit_max is not None and value > lim.limit_max) or (lim.limit_min is not None and value < lim.limit_min)


def exceedance_severity(parameter: EnvParameter, value: float) -> Severity:
    lim = LIMITS[parameter]
    if parameter == EnvParameter.WATER_PH:
        off = max((lim.limit_min or 0) - value, value - (lim.limit_max or 14))
        return Severity.HIGH if off >= 1.5 else Severity.MEDIUM
    ratio = value / (lim.limit_max or 1)
    if ratio >= 2.0:
        return Severity.CRITICAL
    if ratio >= 1.5:
        return Severity.HIGH
    return Severity.MEDIUM


def _limit_text(lim: Limit) -> str:
    if lim.limit_min is not None and lim.limit_max is not None:
        return f"{lim.limit_min}–{lim.limit_max} {lim.unit}"
    return f"{lim.limit_max} {lim.unit}"


# ============================================================== environment
def reading_query(principal: Principal) -> Select[Any]:
    return scope_mines(select(EnvironmentReading), principal, EnvironmentReading.mine_id)


async def list_readings(
    session: AsyncSession, principal: Principal, *, mine_id: uuid.UUID | None, parameter: EnvParameter | None,
    exceeded: bool | None, offset: int, limit: int,
) -> tuple[list[EnvironmentReading], int]:
    stmt = reading_query(principal)
    if mine_id:
        stmt = stmt.where(EnvironmentReading.mine_id == mine_id)
    if parameter:
        stmt = stmt.where(EnvironmentReading.parameter == parameter)
    if exceeded is not None:
        stmt = stmt.where(EnvironmentReading.exceeded.is_(exceeded))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(
        stmt.order_by(EnvironmentReading.sampled_at.desc()).offset(offset).limit(limit)
    )).scalars().unique().all()
    return list(rows), int(total)


async def _open_system_violation(session: AsyncSession, mine_id: uuid.UUID, title_prefix: str) -> Violation | None:
    """An exceedance of the same parameter already open this week — link to it instead of duplicating."""
    since = datetime.now(UTC) - timedelta(days=7)
    return (await session.execute(
        select(Violation).where(
            Violation.mine_id == mine_id,
            Violation.detected_by == DetectedBy.SYSTEM,
            Violation.status != ViolationStatus.CLOSED,
            Violation.title.startswith(title_prefix),
            Violation.occurred_at >= since,
        ).order_by(Violation.occurred_at.desc()).limit(1)
    )).scalars().first()


async def raise_exceedance(session: AsyncSession, mine: Mine, r: EnvironmentReading,
                           principal: Principal | None, *, seeded: bool = False) -> tuple[Violation, bool]:
    lim = LIMITS[r.parameter]
    prefix = f"{lim.label} above statutory limit"
    existing = await _open_system_violation(session, mine.id, prefix)
    if existing:
        return existing, False
    severity = exceedance_severity(r.parameter, r.value)
    v = Violation(
        mine_id=mine.id,
        kind=ViolationKind.VIOLATION,
        category=ComplianceCategory.ENVIRONMENT,
        title=f"{prefix} at {r.station}"[:300],
        description=(
            f"{lim.label} measured {r.value:g} {lim.unit} at {r.station} on "
            f"{r.sampled_at:%d %b %Y %H:%M} UTC against a permissible limit of {_limit_text(lim)} "
            f"({lim.standard}). Recorded automatically from the environmental monitoring register; "
            "identify the source and assign corrective action (e.g. water sprinkling, effluent treatment, "
            "noise barriers)."
        ),
        severity=severity,
        severity_confirmed=True,  # an objective measurement: the AI must not downgrade it
        detected_by=DetectedBy.SYSTEM,
        regulation_ref=lim.standard[:200],
        latitude=r.latitude,
        longitude=r.longitude,
        occurred_at=r.sampled_at,
        reported_by=principal.id if principal else None,
    )
    session.add(v)
    await session.flush()
    v.workflow_id = escalation_workflow_id(v.id)
    record_event(
        session, "violation.flagged", entity_type="violation", entity_id=v.id, actor=None,
        mine_id=mine.id, subsidiary_id=mine.subsidiary_id, after=snapshot(v, V_FIELDS),
        data={"severity": severity.value, "kind": v.kind.value, "category": v.category.value,
              "contractor_id": None, "detected_by": "system", "reading_id": str(r.id),
              **({"seeded": True} if seeded else {})},
    )
    return v, True


async def record_reading(
    session: AsyncSession, principal: Principal | None, data: EnvReadingCreate, *, commit: bool = True,
    seeded: bool = False,
) -> EnvironmentReading:
    if principal is not None:
        principal.require(Perm.OPERATIONS_WRITE)
        mine = await assert_mine_access(session, principal, data.mine_id, write=True)
    else:
        mine = await session.get(Mine, data.mine_id)
        if mine is None:
            raise NotFound("Mine not found")
    lim = LIMITS[data.parameter]
    r = EnvironmentReading(
        mine_id=mine.id,
        parameter=data.parameter,
        value=data.value,
        unit=lim.unit,
        limit_min=lim.limit_min,
        limit_max=lim.limit_max,
        exceeded=is_exceeded(data.parameter, data.value),
        station=data.station,
        sampled_at=data.sampled_at or datetime.now(UTC),
        source=data.source,
        latitude=data.geo.latitude if data.geo else None,
        longitude=data.geo.longitude if data.geo else None,
        notes=data.notes,
        recorded_by=principal.id if principal else None,
    )
    session.add(r)
    await session.flush()
    created = False
    if r.exceeded and not seeded:
        v, created = await raise_exceedance(session, mine, r, principal)
        r.violation_id = v.id
    if not seeded:
        record_event(
            session, "environment.recorded", entity_type="environment_reading", entity_id=r.id, actor=principal,
            mine_id=mine.id, subsidiary_id=mine.subsidiary_id, after=snapshot(r, R_FIELDS),
            data={"exceeded": r.exceeded, "violation_id": str(r.violation_id) if r.violation_id else None,
                  "violation_created": created, "label": lim.label},
        )
    if commit:
        await session.commit()
        return await get_reading(session, principal, r.id) if principal else r
    return r


async def get_reading(session: AsyncSession, principal: Principal, reading_id: uuid.UUID) -> EnvironmentReading:
    r = (await session.execute(reading_query(principal).where(EnvironmentReading.id == reading_id))).scalars().first()
    if r is None:
        raise NotFound("Reading not found")
    return r


async def environment_summary(session: AsyncSession, principal: Principal, mine_id: uuid.UUID | None) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=30)
    base = scope_mines(select(EnvironmentReading), principal, EnvironmentReading.mine_id)
    if mine_id:
        base = base.where(EnvironmentReading.mine_id == mine_id)
    sub = base.subquery()
    agg = (await session.execute(
        select(sub.c.parameter, func.count(), func.avg(sub.c.value),
               func.count().filter(sub.c.exceeded.is_(True)))
        .where(sub.c.sampled_at >= since).group_by(sub.c.parameter)
    )).all()
    stats = {p: (n, avg, exc) for p, n, avg, exc in agg}
    latest_rows = (await session.execute(
        select(sub.c.parameter, sub.c.value, sub.c.sampled_at)
        .distinct(sub.c.parameter).order_by(sub.c.parameter, sub.c.sampled_at.desc())
    )).all()
    latest = {p: (v, at) for p, v, at in latest_rows}
    params = []
    for p, lim in LIMITS.items():
        n, avg, exc = stats.get(p, (0, None, 0))
        lv, lat = latest.get(p, (None, None))
        params.append({
            "parameter": p, "label": lim.label, "unit": lim.unit, "group": lim.group,
            "limit_min": lim.limit_min, "limit_max": lim.limit_max,
            "latest": lv, "latest_at": lat, "average_30d": round(avg, 2) if avg is not None else None,
            "readings_30d": n, "exceedances_30d": exc,
        })
    total = sum(s[0] for s in stats.values())
    exceedances = sum(s[2] for s in stats.values())
    worst = (await session.execute(
        select(Mine.id, Mine.code, Mine.name, func.count())
        .join(sub, sub.c.mine_id == Mine.id)
        .where(sub.c.exceeded.is_(True), sub.c.sampled_at >= since)
        .group_by(Mine.id, Mine.code, Mine.name).order_by(func.count().desc()).limit(5)
    )).all()
    return {
        "parameters": params,
        "readings_30d": total,
        "exceedances_30d": exceedances,
        "compliance_pct": round(100.0 * (total - exceedances) / total, 1) if total else None,
        "worst_mines": [{"mine_id": str(i), "code": c, "name": n, "exceedances": k} for i, c, n, k in worst],
    }


async def environment_trend(session: AsyncSession, principal: Principal, parameter: EnvParameter,
                            mine_id: uuid.UUID | None, days: int) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    stmt = scope_mines(select(EnvironmentReading), principal, EnvironmentReading.mine_id).where(
        EnvironmentReading.parameter == parameter, EnvironmentReading.sampled_at >= since)
    if mine_id:
        stmt = stmt.where(EnvironmentReading.mine_id == mine_id)
    sub = stmt.subquery()
    day = func.date_trunc("day", sub.c.sampled_at)
    rows = (await session.execute(
        select(day, func.avg(sub.c.value), func.max(sub.c.value)).group_by(day).order_by(day)
    )).all()
    return [{"day": d.date(), "average": round(a, 2), "maximum": round(m, 2)} for d, a, m in rows]


# =============================================================== production
def production_query(principal: Principal) -> Select[Any]:
    return scope_mines(select(ProductionRecord), principal, ProductionRecord.mine_id)


async def list_production(
    session: AsyncSession, principal: Principal, *, mine_id: uuid.UUID | None, offset: int, limit: int,
) -> tuple[list[ProductionRecord], int]:
    stmt = production_query(principal)
    if mine_id:
        stmt = stmt.where(ProductionRecord.mine_id == mine_id)
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await session.execute(
        stmt.order_by(ProductionRecord.period.desc(), ProductionRecord.mine_id).offset(offset).limit(limit)
    )).scalars().unique().all()
    return list(rows), int(total)


async def production_anomalies(session: AsyncSession, mine: Mine, rec: ProductionRecord, *,
                               seeded: bool = False) -> int:
    prior = (await session.execute(
        select(ProductionRecord.produced_t).where(
            ProductionRecord.mine_id == mine.id, ProductionRecord.period < rec.period,
            ProductionRecord.period >= rec.period - timedelta(days=100),
        )
    )).scalars().all()
    findings: list[tuple[str, str, str, dict[str, Any], float]] = []
    if prior:
        avg = sum(prior) / len(prior)
        if avg > 0 and rec.produced_t < 0.65 * avg:
            drop = round(100 * (1 - rec.produced_t / avg), 1)
            findings.append((
                f"production-drop:{mine.id}:{rec.period.isoformat()}",
                f"Production fell {drop}% at {mine.name}",
                f"{rec.period:%b %Y} output of {rec.produced_t:,.0f} t is {drop}% below the trailing "
                f"3-month average ({avg:,.0f} t). Check for equipment downtime, safety stoppages or misreporting.",
                {"produced_t": rec.produced_t, "trailing_avg_t": round(avg, 1), "drop_pct": drop},
                min(drop / 100, 1.0),
            ))
    if rec.produced_t > 0 and rec.dispatched_t > 1.25 * rec.produced_t and not rec.closing_stock_t:
        ratio = round(rec.dispatched_t / rec.produced_t, 2)
        findings.append((
            f"dispatch-gap:{mine.id}:{rec.period.isoformat()}",
            f"Despatch exceeds production at {mine.name}",
            f"{rec.period:%b %Y} despatch ({rec.dispatched_t:,.0f} t) is {ratio}× production "
            f"({rec.produced_t:,.0f} t) with no closing stock reported. Reconcile stock and weighbridge records.",
            {"produced_t": rec.produced_t, "dispatched_t": rec.dispatched_t, "ratio": ratio},
            min((ratio - 1), 1.0),
        ))
    created = 0
    for fingerprint, title, description, metric, score in findings:
        exists = (await session.execute(
            select(Anomaly.id).where(Anomaly.fingerprint == fingerprint, Anomaly.status == AnomalyStatus.OPEN)
        )).first()
        if exists:
            continue
        a = Anomaly(mine_id=mine.id, kind=AnomalyKind.OPERATIONAL, fingerprint=fingerprint, title=title,
                    description=description, metric=metric, score=score)
        session.add(a)
        await session.flush()
        record_event(
            session, "anomaly.detected", entity_type="anomaly", entity_id=a.id, actor=None,
            mine_id=mine.id, subsidiary_id=mine.subsidiary_id,
            data={"kind": "operational", "title": title, "description": description, "score": score,
                  **({"seeded": True} if seeded else {})},
        )
        created += 1
    return created


async def upsert_production(session: AsyncSession, principal: Principal, data: ProductionUpsert) -> ProductionRecord:
    principal.require(Perm.OPERATIONS_WRITE)
    mine = await assert_mine_access(session, principal, data.mine_id, write=True)
    rec = (await session.execute(
        select(ProductionRecord).where(ProductionRecord.mine_id == mine.id, ProductionRecord.period == data.period)
    )).scalars().first()
    before = snapshot(rec, P_FIELDS) if rec else None
    if rec is None:
        rec = ProductionRecord(mine_id=mine.id, period=data.period)
        session.add(rec)
    for field in ("target_t", "produced_t", "dispatched_t", "overburden_bcm", "closing_stock_t", "notes"):
        setattr(rec, field, getattr(data, field))
    rec.recorded_by = principal.id
    await session.flush()
    await production_anomalies(session, mine, rec)
    record_event(
        session, "production.updated" if before else "production.recorded", entity_type="production_record",
        entity_id=rec.id, actor=principal, mine_id=mine.id, subsidiary_id=mine.subsidiary_id,
        before=before, after=snapshot(rec, P_FIELDS),
    )
    await session.commit()
    return (await session.execute(production_query(principal).where(ProductionRecord.id == rec.id))).scalars().one()


def _fy_start(today: date) -> date:
    """Indian financial year starts on 1 April."""
    return date(today.year if today.month >= 4 else today.year - 1, 4, 1)


async def production_summary(session: AsyncSession, principal: Principal, mine_id: uuid.UUID | None,
                             months: int = 12) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    # The last `months` returns up to and including the current month (usually filed a month in arrears).
    start = add_months(today.replace(day=1), -months)
    base = production_query(principal)
    if mine_id:
        base = base.where(ProductionRecord.mine_id == mine_id)
    sub = base.subquery()
    rows = (await session.execute(
        select(sub.c.period, func.coalesce(func.sum(sub.c.target_t), 0), func.sum(sub.c.produced_t),
               func.sum(sub.c.dispatched_t), func.coalesce(func.sum(sub.c.overburden_bcm), 0))
        .where(sub.c.period >= start).group_by(sub.c.period).order_by(sub.c.period)
    )).all()
    points = [{"period": p, "target_t": float(t), "produced_t": float(pr), "dispatched_t": float(d),
               "overburden_bcm": float(ob)} for p, t, pr, d, ob in rows][-months:]
    fy = _fy_start(today)
    ytd = [p for p in points if p["period"] >= fy]
    ytd_target = sum(p["target_t"] for p in ytd)
    ytd_prod = sum(p["produced_t"] for p in ytd)
    change = None
    if len(points) >= 2 and points[-2]["produced_t"]:
        change = round(100 * (points[-1]["produced_t"] / points[-2]["produced_t"] - 1), 1)
    shortfall: list[dict[str, Any]] = []
    if points:
        last = points[-1]["period"]
        rows = (await session.execute(
            select(Mine.id, Mine.code, Mine.name, sub.c.produced_t, sub.c.target_t)
            .join(sub, sub.c.mine_id == Mine.id)
            .where(sub.c.period == last, sub.c.target_t > 0, sub.c.produced_t < 0.85 * sub.c.target_t)
            .order_by(sub.c.produced_t / sub.c.target_t).limit(6)
        )).all()
        shortfall = [{"mine_id": str(i), "code": c, "name": n, "produced_t": pr, "target_t": t,
                      "achievement_pct": round(100 * pr / t, 1)} for i, c, n, pr, t in rows]
    return {
        "months": points,
        "ytd_produced_t": ytd_prod,
        "ytd_dispatched_t": sum(p["dispatched_t"] for p in ytd),
        "ytd_target_t": ytd_target,
        "achievement_pct": round(100 * ytd_prod / ytd_target, 1) if ytd_target else None,
        "last_month_change_pct": change,
        "shortfall_mines": shortfall,
    }
