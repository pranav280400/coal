"""Role-scoped dashboard aggregates (FR3, FR12), served from Redis and refreshed by consumers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import cache_get_json, cache_set_json
from app.models import Anomaly, ComplianceItem, Contract, Contractor, Inspection, Mine, Violation
from app.models.enums import (
    AnomalyStatus,
    ComplianceStatus,
    ContractorStatus,
    Role,
    Severity,
    ViolationStatus,
)
from app.services import compliance as compliance_svc
from app.services.access import Principal, scope_mines

DASH_PREFIX = "cmg:dash:"


def scope_key(principal: Principal) -> str:
    if principal.is_global:
        return "global"
    if principal.role == Role.MINE_OFFICIAL:
        return f"mine:{principal.mine_id}"
    if principal.role == Role.CONTRACTOR:
        return f"contractor:{principal.contractor_id}"
    return f"sub:{principal.subsidiary_id}"


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _shift_month(d: date, months: int) -> date:
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1)


async def mine_map_points(session: AsyncSession, principal: Principal) -> list[dict[str, Any]]:
    open_v = (
        select(
            Violation.mine_id.label("mine_id"),
            func.count().label("open"),
            func.count().filter(Violation.severity == Severity.CRITICAL).label("critical"),
        )
        .where(Violation.status != ViolationStatus.CLOSED)
        .group_by(Violation.mine_id)
        .subquery()
    )
    comp = (
        select(
            ComplianceItem.mine_id.label("mine_id"),
            func.count().label("total"),
            func.count().filter(ComplianceItem.status == ComplianceStatus.OVERDUE).label("overdue"),
            func.count()
            .filter(ComplianceItem.status.in_([ComplianceStatus.COMPLIANT, ComplianceStatus.DUE]))
            .label("ok"),
        )
        .group_by(ComplianceItem.mine_id)
        .subquery()
    )
    stmt = scope_mines(
        select(
            Mine,
            func.coalesce(open_v.c.open, 0),
            func.coalesce(open_v.c.critical, 0),
            func.coalesce(comp.c.overdue, 0),
            func.coalesce(comp.c.total, 0),
            func.coalesce(comp.c.ok, 0),
        )
        .outerjoin(open_v, open_v.c.mine_id == Mine.id)
        .outerjoin(comp, comp.c.mine_id == Mine.id)
        .where(Mine.is_active.is_(True)),
        principal,
        Mine.id,
    )
    points = []
    for mine, open_count, critical, overdue, total, ok in (await session.execute(stmt)).unique().all():
        if critical > 0 or overdue >= 3:
            status = "non_compliant"
        elif open_count > 0 or overdue > 0:
            status = "minor_issues"
        else:
            status = "compliant"
        points.append(
            {
                "id": str(mine.id),
                "code": mine.code,
                "name": mine.name,
                "subsidiary_code": mine.subsidiary.code,
                "latitude": mine.latitude,
                "longitude": mine.longitude,
                "status": status,
                "open_violations": int(open_count),
                "critical_violations": int(critical),
                "overdue_compliance": int(overdue),
                "compliance_rate": round(100.0 * ok / total, 1) if total else 100.0,
                "risk_score": mine.risk_score,
            }
        )
    return points


async def violation_trends(session: AsyncSession, principal: Principal, months: int = 6) -> list[dict[str, Any]]:
    today = datetime.now(UTC).date()
    start = _shift_month(_month_start(today), -(months - 1))
    start_dt = datetime(start.year, start.month, 1, tzinfo=UTC)
    month = func.date_trunc("month", Violation.occurred_at)
    stmt = scope_mines(
        select(
            month.label("m"),
            func.count(),
            func.count().filter(Violation.severity == Severity.CRITICAL),
            func.count().filter(Violation.severity == Severity.HIGH),
        )
        .where(Violation.occurred_at >= start_dt)
        .group_by("m"),
        principal,
        Violation.mine_id,
    )
    raised = {row[0].date().replace(day=1): (row[1], row[2], row[3]) for row in (await session.execute(stmt)).all()}
    closed_month = func.date_trunc("month", Violation.closed_at)
    stmt_closed = scope_mines(
        select(closed_month.label("m"), func.count())
        .where(Violation.closed_at >= start_dt)
        .group_by("m"),
        principal,
        Violation.mine_id,
    )
    resolved = {row[0].date().replace(day=1): row[1] for row in (await session.execute(stmt_closed)).all()}
    out = []
    for i in range(months):
        m = _shift_month(start, i)
        total, critical, major = raised.get(m, (0, 0, 0))
        out.append(
            {"month": m.strftime("%Y-%m"), "label": m.strftime("%b"), "total": int(total),
             # "major" = high severity, "minor" = medium + low (the wording used on the dashboard)
             "critical": int(critical), "major": int(major), "minor": int(total - critical - major),
             "resolved": int(resolved.get(m, 0))}
        )
    return out


async def compute(session: AsyncSession, principal: Principal) -> dict[str, Any]:
    now = datetime.now(UTC)
    today = now.date()
    month_start = datetime(today.year, today.month, 1, tzinfo=UTC)
    prev_month_start = datetime.combine(_shift_month(month_start.date(), -1), datetime.min.time(), tzinfo=UTC)

    mines_total, mines_new = (
        await session.execute(
            scope_mines(
                select(func.count(), func.count().filter(Mine.created_at >= month_start)).where(
                    Mine.is_active.is_(True)
                ),
                principal,
                Mine.id,
            )
        )
    ).one()

    comp = await compliance_svc.summary(session, principal)

    v_open, v_critical = (
        await session.execute(
            scope_mines(
                select(
                    func.count(),
                    func.count().filter(Violation.severity == Severity.CRITICAL),
                ).where(Violation.status != ViolationStatus.CLOSED),
                principal,
                Violation.mine_id,
            )
        )
    ).one()

    insp_total, insp_this, insp_prev = (
        await session.execute(
            scope_mines(
                select(
                    func.count(),
                    func.count().filter(Inspection.inspected_at >= month_start),
                    func.count().filter(
                        and_(Inspection.inspected_at >= prev_month_start, Inspection.inspected_at < month_start)
                    ),
                ),
                principal,
                Inspection.mine_id,
            )
        )
    ).one()
    insp_change = round(100.0 * (insp_this - insp_prev) / insp_prev, 1) if insp_prev else None

    contractor_stmt = select(
        func.count(),
        func.count().filter(Contractor.verified.is_(True)),
    ).where(Contractor.status == ContractorStatus.ACTIVE)
    if not principal.is_global:
        visible = scope_mines(select(Contract.contractor_id), principal, Contract.mine_id)
        contractor_stmt = contractor_stmt.where(Contractor.id.in_(visible))
    c_active, c_verified = (await session.execute(contractor_stmt)).one()

    recent = (
        await session.execute(
            scope_mines(select(Inspection), principal, Inspection.mine_id)
            .order_by(Inspection.inspected_at.desc())
            .limit(6)
        )
    ).scalars().unique().all()

    deadlines = (
        await session.execute(
            scope_mines(select(ComplianceItem), principal, ComplianceItem.mine_id)
            .where(ComplianceItem.status.not_in([ComplianceStatus.COMPLIANT]))
            .order_by(
                case((ComplianceItem.status == ComplianceStatus.OVERDUE, 0), else_=1), ComplianceItem.due_date
            )
            .limit(6)
        )
    ).scalars().unique().all()

    high_risk = (
        await session.execute(
            scope_mines(select(Mine), principal, Mine.id)
            .where(Mine.risk_score.is_not(None))
            .order_by(Mine.risk_score.desc())
            .limit(5)
        )
    ).scalars().unique().all()

    anomalies_open = (
        await session.execute(
            scope_mines(
                select(func.count()).select_from(Anomaly).where(Anomaly.status == AnomalyStatus.OPEN),
                principal,
                Anomaly.mine_id,
            )
        )
    ).scalar_one()

    return {
        "generated_at": now.isoformat(),
        "scope": scope_key(principal),
        "kpis": {
            "total_mines": int(mines_total),
            "new_mines_this_month": int(mines_new),
            "compliance_items": comp["total"],
            "compliance_rate": comp["compliance_rate"],
            "open_violations": int(v_open),
            "critical_violations": int(v_critical),
            "active_contractors": int(c_active),
            "verified_contractors": int(c_verified),
            "inspections": int(insp_total),
            "inspections_this_month": int(insp_this),
            "inspections_change_pct": insp_change,
            "open_anomalies": int(anomalies_open),
        },
        "compliance": comp,
        "recent_inspections": [
            {
                "id": str(i.id),
                "number": i.number,
                "mine_name": i.mine.name,
                "title": i.title,
                "inspection_type": i.inspection_type.value,
                "inspected_at": i.inspected_at.isoformat(),
                "outcome": i.outcome.value,
                "geo_verified": i.geo_verified,
            }
            for i in recent
        ],
        "upcoming_deadlines": [
            {
                "id": str(c.id),
                "title": c.title,
                "mine_name": c.mine.name,
                "due_date": c.due_date.isoformat(),
                "days_left": (c.due_date - today).days,
                "status": c.status.value,
                "category": c.category.value,
            }
            for c in deadlines
        ],
        "violation_trends": await violation_trends(session, principal),
        "mine_locations": await mine_map_points(session, principal),
        "high_risk_mines": [
            {"id": str(m.id), "name": m.name, "code": m.code, "risk_score": m.risk_score} for m in high_risk
        ],
    }


async def get_summary(session: AsyncSession, principal: Principal, *, fresh: bool = False) -> dict[str, Any]:
    key = DASH_PREFIX + scope_key(principal)
    if not fresh:
        try:
            cached = await cache_get_json(key)
            if cached:
                cached["cached"] = True
                return cached
        except Exception:  # cache outage must not break dashboards
            pass
    data = await compute(session, principal)
    try:
        await cache_set_json(key, data, get_settings().dashboard_cache_ttl_seconds)
    except Exception:
        pass
    data["cached"] = False
    return data


def upcoming_cutoff(days: int) -> date:
    return datetime.now(UTC).date() + timedelta(days=days)
