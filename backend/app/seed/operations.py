"""Demo data for grievances, monthly production returns and environmental monitoring.

Idempotent: each block only runs when its table is empty, so it can be applied to a
database that was seeded before these modules existed (``python -m app.cli seed-operations``).
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EnvironmentReading, Grievance, Mine, ProductionRecord, User
from app.models.base import snapshot
from app.models.enums import (
    EnvParameter,
    GrievanceCategory,
    GrievanceStatus,
    MineType,
    Role,
    Severity,
)
from app.seed.demo import MINES
from app.services import grievances as grievance_svc
from app.services import operations as ops_svc
from app.services.compliance import add_months
from app.services.events import record_event

RISK = {code: risk for code, *_rest, risk in MINES}

# (category, priority, subject, description)
GRIEVANCES: list[tuple[GrievanceCategory, Severity, str, str]] = [
    (GrievanceCategory.WAGES, Severity.HIGH, "Contract loaders paid below notified minimum wage",
     "Loaders engaged through the transport contractor received wages for last month at a rate below the "
     "notified minimum wage for underground/opencast unskilled workers. Wage slips attached with the complaint."),
    (GrievanceCategory.WAGES, Severity.MEDIUM, "Wages delayed by more than 15 days",
     "Wages for the second half of the month have not been credited. Workers were told the contractor's "
     "bill is pending with the area office."),
    (GrievanceCategory.SAFETY, Severity.CRITICAL, "No lighting on haul road bend near Seam III",
     "The haul road bend below the Seam III bench has had no working lights for a week. Dumpers pass within "
     "a metre of the berm during the night shift."),
    (GrievanceCategory.SAFETY, Severity.HIGH, "Dust masks not issued to night-shift drill operators",
     "Drill operators on the night shift have not been issued replacement dust masks for three weeks; the "
     "PPE store says stock is exhausted."),
    (GrievanceCategory.SAFETY, Severity.HIGH, "Rest shelter too close to the blasting danger zone",
     "The new rest shelter for contract workers is inside the 300 m blasting danger zone. Workers are asked "
     "to stay inside during blasts."),
    (GrievanceCategory.WORKING_CONDITIONS, Severity.MEDIUM, "No drinking water at the east bench workface",
     "The water tanker for the east bench has not come for four days. The nearest drinking water point is "
     "over a kilometre away."),
    (GrievanceCategory.WORKING_CONDITIONS, Severity.LOW, "Canteen closed during the night shift",
     "The canteen closes at 10 pm and night-shift workers have no access to food or tea."),
    (GrievanceCategory.HARASSMENT, Severity.HIGH, "Verbal abuse by a shift supervisor",
     "A shift supervisor repeatedly abuses and threatens contract workers who ask for leave. Raised "
     "anonymously for fear of losing work."),
    (GrievanceCategory.WELFARE, Severity.MEDIUM, "Periodical medical examination overdue for contract workers",
     "About 30 contract workers have not had their periodical medical examination for more than five years, "
     "as required under the Mines Rules."),
    (GrievanceCategory.WELFARE, Severity.LOW, "Irregular water supply in the workers' colony",
     "Water supply in Block C of the colony comes only on alternate days."),
    (GrievanceCategory.CONTRACTOR_DISPUTE, Severity.MEDIUM, "Overtime not paid by the contractor",
     "Overtime worked during the pre-monsoon de-watering drive has not been paid by the contractor."),
    (GrievanceCategory.CONTRACTOR_DISPUTE, Severity.HIGH, "Provident fund deductions not deposited",
     "PF is being deducted from wages but the CMPF passbook shows no deposits for the last four months."),
    (GrievanceCategory.ENVIRONMENT, Severity.MEDIUM, "Coal dust from transport road affecting the village",
     "Uncovered trucks and a dry transport road are coating houses and crops in the adjoining village with "
     "coal dust. Villagers ask for water sprinkling and covered transport."),
    (GrievanceCategory.ENVIRONMENT, Severity.HIGH, "Blasting vibrations cracking houses in buffer village",
     "Residents report new cracks in houses after the recent heavy blasts; they ask for vibration monitoring "
     "and controlled blasting."),
    (GrievanceCategory.OTHER, Severity.LOW, "Shift bus service discontinued",
     "The bus from the township to the pit for the first shift has been withdrawn, so workers walk 6 km."),
]

RESOLUTIONS = {
    GrievanceCategory.WAGES: "Arrears computed at the notified rate and paid through bank transfer; contractor "
                             "warned and wage register verified by the welfare officer.",
    GrievanceCategory.SAFETY: "Issue fixed on site and verified during the next shift inspection; added to the "
                              "daily safety checklist.",
    GrievanceCategory.WORKING_CONDITIONS: "Arrangement restored and a standing instruction issued to the "
                                          "section in-charge.",
    GrievanceCategory.WELFARE: "Camp scheduled with the area hospital; list of workers shared with the "
                               "contractor and union.",
    GrievanceCategory.CONTRACTOR_DISPUTE: "Contractor directed to settle dues within 7 days; payment "
                                          "verified against bank statements.",
    GrievanceCategory.ENVIRONMENT: "Additional mist sprinklers deployed and tarpaulin covering made mandatory "
                                   "at the weighbridge.",
    GrievanceCategory.HARASSMENT: "Enquiry by the internal committee completed; supervisor counselled and "
                                  "moved to another section.",
    GrievanceCategory.OTHER: "Service restored from the next month after discussion with the transport "
                             "department.",
}

STATUS_MIX = [
    GrievanceStatus.OPEN, GrievanceStatus.OPEN, GrievanceStatus.ASSIGNED, GrievanceStatus.ASSIGNED,
    GrievanceStatus.IN_PROGRESS, GrievanceStatus.IN_PROGRESS, GrievanceStatus.RESOLVED,
    GrievanceStatus.CLOSED, GrievanceStatus.CLOSED, GrievanceStatus.CLOSED, GrievanceStatus.REJECTED,
]


async def _count(session: AsyncSession, model: Any) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


# ================================================================ production
async def seed_production(session: AsyncSession, mines: list[Mine], rng: random.Random, today: date) -> dict[str, int]:
    this_month = today.replace(day=1)
    records: list[ProductionRecord] = []
    for mine in mines:
        risk = RISK.get(mine.code, 0.5)
        monthly_target = (mine.capacity_mtpa or 1.0) * 1_000_000 / 12
        stripping = 0.15 if mine.mine_type == MineType.UNDERGROUND else rng.uniform(2.4, 4.2)
        stock = monthly_target * rng.uniform(0.2, 0.6)
        for back in range(12, 0, -1):
            period = add_months(this_month, -back)
            monsoon = 0.82 if period.month in (7, 8, 9) else 1.0
            # Higher-risk mines run less reliably below target.
            produced = monthly_target * monsoon * rng.uniform(0.98 - 0.22 * risk, 1.1 - 0.1 * risk)
            if mine.code == "BCCL-BST" and back == 1:
                produced *= 0.5  # a stoppage last month — surfaces as an operational anomaly
            dispatched = produced * rng.uniform(0.9, 1.04)
            stock = max(stock + produced - dispatched, 0)
            records.append(ProductionRecord(
                mine_id=mine.id, period=period, target_t=round(monthly_target * monsoon, -2),
                produced_t=round(produced, -1), dispatched_t=round(dispatched, -1),
                overburden_bcm=round(produced * stripping, -2), closing_stock_t=round(stock, -1),
            ))
    session.add_all(records)
    await session.flush()
    anomalies = 0
    last = add_months(this_month, -1)
    for mine in mines:
        rec = next(r for r in records if r.mine_id == mine.id and r.period == last)
        anomalies += await ops_svc.production_anomalies(session, mine, rec, seeded=True)
    return {"production_records": len(records), "production_anomalies": anomalies}


# =============================================================== environment
_VILLAGES = ["Kulda", "Balram", "Hingula", "Tentuloi", "Kaniha", "Gevra Basti", "Nigahi Tola", "Jhariagarh"]


async def seed_environment(session: AsyncSession, mines: list[Mine], rng: random.Random,
                           now: datetime) -> dict[str, int]:
    readings: list[EnvironmentReading] = []

    def add(mine: Mine, p: EnvParameter, value: float, station: str, at: datetime, source: str) -> None:
        lim = ops_svc.LIMITS[p]
        readings.append(EnvironmentReading(
            mine_id=mine.id, parameter=p, value=round(value, 1 if p != EnvParameter.WATER_PH else 2),
            unit=lim.unit, limit_min=lim.limit_min, limit_max=lim.limit_max,
            exceeded=ops_svc.is_exceeded(p, value), station=station, sampled_at=at, source=source,
            latitude=mine.latitude + rng.uniform(-0.01, 0.01), longitude=mine.longitude + rng.uniform(-0.01, 0.01),
        ))

    for i, mine in enumerate(mines):
        risk = RISK.get(mine.code, 0.5)
        opencast = mine.mine_type != MineType.UNDERGROUND
        stations = ["Core zone AAQ station", f"Buffer zone — {_VILLAGES[i % len(_VILLAGES)]} village"]
        for week in range(17, -1, -1):
            day = (now - timedelta(days=7 * week + rng.randint(0, 2))).date()
            at = datetime.combine(day, time(rng.randint(4, 10), 0), tzinfo=UTC)
            dry = at.month in (3, 4, 5, 11, 12, 1, 2)
            for s_idx, station in enumerate(stations):
                buffer = 0.72 if s_idx else 1.0
                dust = (55 + 75 * risk) * (1.15 if dry else 0.85) * (1.1 if opencast else 0.8) * buffer
                add(mine, EnvParameter.PM10, dust * rng.uniform(0.78, 1.22), station, at, "sensor")
                add(mine, EnvParameter.PM2_5, dust * 0.46 * rng.uniform(0.75, 1.2), station, at, "sensor")
                add(mine, EnvParameter.SO2, rng.uniform(12, 34) * (1 + 0.4 * risk) * buffer, station, at, "sensor")
                add(mine, EnvParameter.NO2, rng.uniform(16, 42) * (1 + 0.4 * risk) * buffer, station, at, "sensor")
            add(mine, EnvParameter.NOISE_DAY, rng.uniform(62, 71) + 6 * risk, "Haul road — weighbridge", at, "manual")
            add(mine, EnvParameter.NOISE_NIGHT, rng.uniform(55, 64) + 7 * risk, "Haul road — weighbridge",
                at + timedelta(hours=14), "manual")
            if week % 2 == 0:
                lab_at = at + timedelta(hours=6)
                outlet = "Mine discharge point (ETP outlet)"
                add(mine, EnvParameter.WATER_PH, rng.uniform(6.6, 8.3) - (1.4 * risk if rng.random() < 0.08 else 0),
                    outlet, lab_at, "lab")
                add(mine, EnvParameter.WATER_TSS, rng.uniform(35, 80) * (1 + 0.55 * risk), outlet, lab_at, "lab")
                add(mine, EnvParameter.WATER_OIL_GREASE, rng.uniform(2, 7) * (1 + 0.6 * risk), outlet, lab_at, "lab")
                add(mine, EnvParameter.WATER_COD, rng.uniform(70, 170) * (1 + 0.3 * risk), outlet, lab_at, "lab")
    session.add_all(readings)
    await session.flush()

    # Exceedances in the last 10 days open live violations (as a new reading would).
    violations = 0
    recent = now - timedelta(days=10)
    by_mine = {m.id: m for m in mines}
    seen: set[tuple[Any, EnvParameter]] = set()
    for r in sorted(readings, key=lambda x: x.sampled_at, reverse=True):
        if not r.exceeded or r.sampled_at < recent or (r.mine_id, r.parameter) in seen:
            continue
        seen.add((r.mine_id, r.parameter))
        v, created = await ops_svc.raise_exceedance(session, by_mine[r.mine_id], r, None, seeded=True)
        r.violation_id = v.id
        violations += int(created)
    return {"environment_readings": len(readings),
            "exceedances": sum(1 for r in readings if r.exceeded), "exceedance_violations": violations}


# ================================================================ grievances
async def seed_grievances(session: AsyncSession, mines: list[Mine], rng: random.Random,
                          now: datetime) -> dict[str, int]:
    users = (await session.execute(select(User))).scalars().unique().all()
    officials = {u.mine_id: u for u in users if u.role == Role.MINE_OFFICIAL and u.mine_id}
    corporate_by_sub = {u.subsidiary_id: u for u in users if u.role == Role.CORPORATE and u.subsidiary_id}
    hq = next((u for u in users if u.role == Role.CORPORATE and u.subsidiary_id is None), None)
    contractor = next((u for u in users if u.role == Role.CONTRACTOR), None)
    from app.models import Contract

    contractor_mines = set((await session.execute(
        select(Contract.mine_id).where(Contract.contractor_id == contractor.contractor_id)
    )).scalars().all()) if contractor and contractor.contractor_id else set()

    created: list[Grievance] = []
    pool = sorted(mines, key=lambda m: -RISK.get(m.code, 0.5))
    for n in range(42):
        mine = pool[n % len(pool)] if n < 30 else rng.choice(pool)
        category, priority, subject, description = GRIEVANCES[(n * 7) % len(GRIEVANCES)]
        official = officials.get(mine.id)
        if official is None:
            continue
        # Contract workers' complaints come through the contractor's site in-charge where it has a contract.
        by_contractor = contractor is not None and mine.id in contractor_mines and category in (
            GrievanceCategory.WAGES, GrievanceCategory.CONTRACTOR_DISPUTE, GrievanceCategory.WELFARE,
            GrievanceCategory.WORKING_CONDITIONS)
        raiser = contractor if by_contractor else official
        manager = official if by_contractor else (corporate_by_sub.get(mine.subsidiary_id) or hq)
        status = STATUS_MIX[n % len(STATUS_MIX)]
        created_at = now - timedelta(days=rng.randint(1, 58), hours=rng.randint(0, 23))
        g = Grievance(
            mine_id=mine.id, raised_by=raiser.id,
            contractor_id=raiser.contractor_id if raiser.role == Role.CONTRACTOR else None,
            is_anonymous=category == GrievanceCategory.HARASSMENT or rng.random() < 0.12,
            category=category, subject=subject, description=description, priority=priority,
            status=status, due_at=grievance_svc.sla_due(priority, created_at),
        )
        g.created_at = created_at
        if status != GrievanceStatus.OPEN and manager:
            g.assigned_to = manager.id
        if status in (GrievanceStatus.RESOLVED, GrievanceStatus.CLOSED, GrievanceStatus.REJECTED):
            spent = timedelta(hours=grievance_svc.SLA_HOURS[priority] * rng.uniform(0.3, 1.3))
            g.resolved_at = min(created_at + spent, now - timedelta(hours=2))
            g.resolved_by = manager.id if manager else None
            g.resolution_notes = (RESOLUTIONS[category] if status != GrievanceStatus.REJECTED else
                                  "Checked the attendance and payment registers; the claim is not supported by "
                                  "records. The worker may reopen with further evidence.")
        if status == GrievanceStatus.CLOSED:
            g.closed_at = g.resolved_at + timedelta(hours=rng.randint(4, 60)) if g.resolved_at else now
            g.closed_at = min(g.closed_at, now)
            g.satisfaction = rng.choice([3, 4, 4, 5, 5, 2])
        if status in (GrievanceStatus.OPEN, GrievanceStatus.ASSIGNED, GrievanceStatus.IN_PROGRESS) and g.due_at < now:
            g.escalation_level = min(1 + int((now - g.due_at).days // 3), 3)
        session.add(g)
        created.append(g)
    await session.flush()
    for g in created:
        await session.refresh(g, ["mine"])
        record_event(
            session, "grievance.raised", entity_type="grievance", entity_id=g.id, actor=None,
            mine_id=g.mine_id, subsidiary_id=g.mine.subsidiary_id, after=snapshot(g, grievance_svc.G_FIELDS),
            data={"number": g.number, "subject": g.subject, "priority": g.priority.value,
                  "category": g.category.value, "mine_name": g.mine.name, "seeded": True},
            occurred_at=g.created_at,
        )
    return {"grievances": len(created)}


async def seed_operations(session: AsyncSession) -> dict[str, Any]:
    rng = random.Random(26025)
    now = datetime.now(UTC)
    mines = list((await session.execute(select(Mine).order_by(Mine.code))).scalars().unique().all())
    if not mines:
        return {"skipped": "no mines — run seed-demo first"}
    summary: dict[str, Any] = {}
    if not await _count(session, ProductionRecord):
        summary |= await seed_production(session, mines, rng, now.date())
    if not await _count(session, EnvironmentReading):
        summary |= await seed_environment(session, mines, rng, now)
    if not await _count(session, Grievance):
        summary |= await seed_grievances(session, mines, rng, now)
    return summary or {"skipped": "operations data already present"}
