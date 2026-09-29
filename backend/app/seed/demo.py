"""Demo/UAT dataset: CIL subsidiaries, real coalfield locations, 12 months of history.

Deterministic (fixed RNG seed) so every environment gets the same baseline. Never
run in production — the CLI refuses unless ENVIRONMENT != production or --force.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import (
    AttendanceRecord,
    ComplianceItem,
    Contract,
    Contractor,
    CorrectiveAction,
    Inspection,
    Mine,
    Regulation,
    Subsidiary,
    User,
    Violation,
)
from app.models.base import snapshot
from app.models.enums import (
    ActionStatus,
    ComplianceCategory,
    ComplianceStatus,
    ContractorStatus,
    ContractStatus,
    DetectedBy,
    Frequency,
    InspectionOutcome,
    InspectionStatus,
    InspectionType,
    MineType,
    Role,
    Severity,
    Shift,
    UserStatus,
    ViolationKind,
    ViolationStatus,
)
from app.seed.regulations import REGULATIONS
from app.services.events import record_event
from app.services.violations import V_FIELDS

DEMO_PASSWORD = "CoalMine@2026"

SUBSIDIARIES = [
    ("MCL", "Mahanadi Coalfields Limited", "Sambalpur, Odisha"),
    ("SECL", "South Eastern Coalfields Limited", "Bilaspur, Chhattisgarh"),
    ("NCL", "Northern Coalfields Limited", "Singrauli, Madhya Pradesh"),
    ("CCL", "Central Coalfields Limited", "Ranchi, Jharkhand"),
    ("BCCL", "Bharat Coking Coal Limited", "Dhanbad, Jharkhand"),
    ("ECL", "Eastern Coalfields Limited", "Sanctoria, West Bengal"),
    ("WCL", "Western Coalfields Limited", "Nagpur, Maharashtra"),
]

# code, name, subsidiary, type, state, district, lat, lon, capacity MTPA, workforce, risk profile (0-1)
MINES = [
    ("MCL-KLG", "Kalinga Opencast Project", "MCL", MineType.OPENCAST, "Odisha", "Angul", 20.955, 85.135, 20.0, 1450, 0.35),
    ("MCL-JGN", "Jagannath Opencast Project", "MCL", MineType.OPENCAST, "Odisha", "Angul", 20.968, 85.162, 12.0, 1180, 0.55),
    ("MCL-LNG", "Lingaraj Opencast Project", "MCL", MineType.OPENCAST, "Odisha", "Angul", 20.921, 85.191, 16.0, 1320, 0.45),
    ("MCL-LKP", "Lakhanpur Opencast Project", "MCL", MineType.OPENCAST, "Odisha", "Jharsuguda", 21.781, 83.862, 20.0, 1500, 0.6),
    ("MCL-BLP", "Belpahar Opencast Project", "MCL", MineType.OPENCAST, "Odisha", "Jharsuguda", 21.842, 83.851, 10.0, 950, 0.3),
    ("SECL-GVR", "Gevra Opencast Project", "SECL", MineType.OPENCAST, "Chhattisgarh", "Korba", 22.333, 82.598, 52.5, 3200, 0.5),
    ("SECL-DPK", "Dipka Opencast Project", "SECL", MineType.OPENCAST, "Chhattisgarh", "Korba", 22.301, 82.531, 35.0, 2600, 0.4),
    ("SECL-KSM", "Kusmunda Opencast Project", "SECL", MineType.OPENCAST, "Chhattisgarh", "Korba", 22.334, 82.681, 50.0, 3000, 0.65),
    ("SECL-RJN", "Rajnagar RO Underground Mine", "SECL", MineType.UNDERGROUND, "Madhya Pradesh", "Anuppur", 23.071, 81.742, 0.8, 780, 0.7),
    ("NCL-JYT", "Jayant Opencast Project", "NCL", MineType.OPENCAST, "Madhya Pradesh", "Singrauli", 24.152, 82.631, 25.0, 2100, 0.35),
    ("NCL-NGH", "Nigahi Opencast Project", "NCL", MineType.OPENCAST, "Madhya Pradesh", "Singrauli", 24.139, 82.582, 22.0, 1900, 0.4),
    ("NCL-DDC", "Dudhichua Opencast Project", "NCL", MineType.OPENCAST, "Uttar Pradesh", "Sonbhadra", 24.171, 82.671, 25.0, 2000, 0.3),
    ("CCL-PPW", "Piparwar Opencast Project", "CCL", MineType.OPENCAST, "Jharkhand", "Chatra", 23.718, 84.951, 10.0, 1100, 0.45),
    ("CCL-RJP", "Rajrappa Opencast Project", "CCL", MineType.OPENCAST, "Jharkhand", "Ramgarh", 23.632, 85.702, 3.0, 850, 0.5),
    ("BCCL-BST", "Bastacolla Mixed Mine", "BCCL", MineType.MIXED, "Jharkhand", "Dhanbad", 23.742, 86.441, 2.5, 1250, 0.85),
    ("BCCL-MND", "Moonidih Underground Project", "BCCL", MineType.UNDERGROUND, "Jharkhand", "Dhanbad", 23.731, 86.332, 1.5, 1400, 0.75),
    ("ECL-RJM", "Rajmahal Opencast Project", "ECL", MineType.OPENCAST, "Jharkhand", "Godda", 25.001, 87.351, 17.0, 1600, 0.55),
    ("ECL-SPB", "Sonepur Bazari Opencast Project", "ECL", MineType.OPENCAST, "West Bengal", "Paschim Bardhaman", 23.632, 87.201, 8.0, 1150, 0.4),
    ("ECL-JHJ", "Jhanjra Underground Project", "ECL", MineType.UNDERGROUND, "West Bengal", "Paschim Bardhaman", 23.621, 87.331, 3.5, 1700, 0.6),
    ("WCL-UMR", "Umrer Opencast Project", "WCL", MineType.OPENCAST, "Maharashtra", "Nagpur", 20.851, 79.331, 3.5, 700, 0.35),
    ("WCL-PDM", "Padmapur Opencast Project", "WCL", MineType.OPENCAST, "Maharashtra", "Chandrapur", 19.991, 79.331, 2.0, 640, 0.45),
]

COMPLIANCE_TEMPLATES = [
    (ComplianceCategory.SAFETY, "Safety Management Plan annual review", "CMR2017-R32", Frequency.ANNUAL),
    (ComplianceCategory.SAFETY, "Haul road & traffic rules audit", "CMR2017-R196", Frequency.QUARTERLY),
    (ComplianceCategory.SAFETY, "Slope stability monitoring report", "CMR2017-R106", Frequency.MONTHLY),
    (ComplianceCategory.SAFETY, "PPE issue register reconciliation", "CMR2017-R191", Frequency.QUARTERLY),
    (ComplianceCategory.SAFETY, "Pre-monsoon inundation preparedness report", "CMR2017-R164", Frequency.ANNUAL),
    (ComplianceCategory.ENVIRONMENT, "Dust Control Compliance — ambient PM10/PM2.5", "AIRACT1981-S21", Frequency.MONTHLY),
    (ComplianceCategory.ENVIRONMENT, "Water Quality Monitoring — mine discharge", "WATERACT1974-S25", Frequency.MONTHLY),
    (ComplianceCategory.ENVIRONMENT, "Half-yearly EC compliance report to MoEFCC", "EC-COND-HALFYEARLY", Frequency.HALF_YEARLY),
    (ComplianceCategory.ENVIRONMENT, "Progressive mine closure progress report", "MCG-CLOSURE", Frequency.ANNUAL),
    (ComplianceCategory.PRODUCTION, "Monthly production & despatch return", "MCDR-RETURNS", Frequency.MONTHLY),
    (ComplianceCategory.PRODUCTION, "Mine plans and sections update", "CMR2017-R58", Frequency.HALF_YEARLY),
    (ComplianceCategory.LABOUR, "Contract labour licence verification", "CLRA1970-S12", Frequency.QUARTERLY),
    (ComplianceCategory.LABOUR, "Periodical medical examination (PME) schedule", "MR1955-R29B", Frequency.QUARTERLY),
    (ComplianceCategory.LABOUR, "CMPF contribution remittance", "CMPF-REMIT", Frequency.MONTHLY),
    (ComplianceCategory.LABOUR, "Vocational refresher training plan", "MVTR1966-R8", Frequency.ANNUAL),
]

VIOLATION_TEMPLATES: list[tuple[ComplianceCategory, Severity, str, str, str]] = [
    (ComplianceCategory.SAFETY, Severity.CRITICAL, "Unsupported roof observed at working face",
     "Roof bolting incomplete over 6 m at the development face; loose strata visible. Persons were working under unsupported roof.",
     "CMR 2017 Reg. 107"),
    (ComplianceCategory.SAFETY, Severity.CRITICAL, "Methane above permissible limit in return airway",
     "Methane reading of 1.3% recorded in the return airway during the shift examination; electrical power was not cut off immediately.",
     "CMR 2017 Reg. 145"),
    (ComplianceCategory.SAFETY, Severity.HIGH, "Dumper operating without functional reversing alarm",
     "Rear-dump truck operating on the haul road without audiovisual reversing alarm and proximity warning device.",
     "CMR 2017 Reg. 196"),
    (ComplianceCategory.SAFETY, Severity.HIGH, "Haul road berm below half wheel height",
     "Safety berm on the outer edge of the haul road near the dump was about 0.6 m, less than half the wheel height of the dumpers operating.",
     "CMR 2017 Reg. 196"),
    (ComplianceCategory.SAFETY, Severity.HIGH, "Tension cracks on bench crest not acted upon",
     "Tension cracks observed along the crest of the third bench; no withdrawal of persons or slope monitoring was in place.",
     "CMR 2017 Reg. 106"),
    (ComplianceCategory.SAFETY, Severity.MEDIUM, "Workers without helmets near shovel operations",
     "Three contract workers were found without helmets and safety shoes within the swing radius of the shovel.",
     "CMR 2017 Reg. 191"),
    (ComplianceCategory.SAFETY, Severity.MEDIUM, "Fire extinguishers past refill date at CHP",
     "Four fire extinguishers at the coal handling plant were past their refill date and the inspection tags were missing.",
     "CMR 2017 Reg. 170"),
    (ComplianceCategory.SAFETY, Severity.LOW, "Shift examination register not countersigned",
     "Shift examination entries for the previous week were not countersigned by the overman.", "CMR 2017"),
    (ComplianceCategory.ENVIRONMENT, Severity.HIGH, "Mine water discharged without treatment",
     "Mine water from the sump was discharged directly into the nallah; TSS visibly high, settling pond bypassed.",
     "Water Act 1974 s.25"),
    (ComplianceCategory.ENVIRONMENT, Severity.MEDIUM, "Fog cannons idle during peak dust hours",
     "Fog cannons along the haul road were not operating between 11:00 and 14:00; visible dust plume at the mine boundary.",
     "Air Act 1981 s.21"),
    (ComplianceCategory.ENVIRONMENT, Severity.MEDIUM, "PM10 exceedance at boundary station",
     "Continuous ambient air quality station recorded PM10 above the notified standard for three consecutive days.",
     "EPA 1986 Schedule I"),
    (ComplianceCategory.ENVIRONMENT, Severity.LOW, "Plantation survival record not maintained",
     "Survival records for the current year's overburden dump plantation were not available for inspection.",
     "Mine Closure Guidelines"),
    (ComplianceCategory.PRODUCTION, Severity.MEDIUM, "Mine plan not updated for current workings",
     "The statutory mine plan had not been updated for the last quarter's workings in the eastern section.",
     "CMR 2017 Reg. 58"),
    (ComplianceCategory.PRODUCTION, Severity.LOW, "Monthly production return submitted late",
     "The monthly production and despatch return was submitted 9 days after the due date.", "Coal Controller returns"),
    (ComplianceCategory.LABOUR, Severity.HIGH, "Contract workers paid below notified wages",
     "Wage slips of a contractor's workers showed payment below the HPC-notified rates for the category of work.",
     "CLRA 1970 s.21"),
    (ComplianceCategory.LABOUR, Severity.MEDIUM, "Contractor licence expired",
     "The contractor's CLRA licence expired last month and renewal was not applied for; workers continued to be deployed.",
     "CLRA 1970 s.12"),
    (ComplianceCategory.LABOUR, Severity.MEDIUM, "Workers deployed without vocational training",
     "Five newly engaged contract workers were deployed in the pit without basic vocational training certificates.",
     "MVT Rules 1966 r.8"),
    (ComplianceCategory.LABOUR, Severity.LOW, "Attendance register incomplete for contractor workers",
     "Form-C attendance entries for contractor workers were incomplete for two shifts.", "Mines Act 1952 s.48"),
]

CHECKLIST = [
    "Haul roads, berms and gradients as per traffic rules",
    "Bench height/width and slope stability",
    "PPE compliance of all persons in the pit",
    "Dust suppression (sprinklers / fog cannons) operational",
    "HEMM brakes, alarms and proximity devices",
    "Fire-fighting equipment serviceable",
    "Statutory registers up to date",
    "Contract worker licences and training records",
    "Mine water treatment and discharge",
    "Electrical installations and earthing",
]

CONTRACTORS = [
    ("Mahanadi Earthmovers Pvt Ltd", "MCL", "Overburden removal"),
    ("Talcher Infra Projects LLP", "MCL", "Haul road maintenance"),
    ("Odisha Mining Services Ltd", "MCL", "Coal transportation"),
    ("Korba Heavy Equipment Co", "SECL", "Overburden removal"),
    ("Chhattisgarh Minetech Pvt Ltd", "SECL", "Blasting services"),
    ("Singrauli Logistics Pvt Ltd", "NCL", "Coal transportation"),
    ("Vindhya Earthworks Ltd", "NCL", "Overburden removal"),
    ("Damodar Mining Contractors", "CCL", "Coal extraction"),
    ("Jharia Safety Solutions", "BCCL", "Fire & safety services"),
    ("Ajay Valley Infrastructure", "ECL", "Overburden removal"),
    ("Vidarbha Minerals & Transport", "WCL", "Coal transportation"),
    ("Rajmahal Civil Works Pvt Ltd", "ECL", "Civil & environmental works"),
]

FIRST = ["Ravi", "Anita", "Suresh", "Priya", "Amit", "Kavita", "Rajesh", "Sunita", "Manoj", "Deepa", "Vikram", "Neha",
         "Arun", "Pooja", "Sanjay", "Meena", "Rahul", "Lata", "Ashok", "Rekha"]
LAST = ["Kumar", "Sharma", "Patnaik", "Singh", "Das", "Mishra", "Verma", "Mahato", "Yadav", "Behera", "Tiwari",
        "Nayak", "Pandey", "Soren", "Rao"]


def _gstin(rng: random.Random, state_code: str) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    pan = "".join(rng.choice(letters) for _ in range(5)) + f"{rng.randint(1000, 9999)}" + rng.choice(letters)
    return f"{state_code}{pan}{rng.randint(1, 9)}Z{rng.choice(letters + '0123456789')}"


async def already_seeded(session: AsyncSession) -> bool:
    return bool((await session.execute(select(func.count()).select_from(Mine))).scalar_one())


async def seed_regulations(session: AsyncSession) -> int:
    existing = set((await session.execute(select(Regulation.code))).scalars().all())
    added = 0
    for r in REGULATIONS:
        if r["code"] not in existing:
            session.add(Regulation(**r))
            added += 1
    await session.flush()
    return added


async def seed_demo(session: AsyncSession, *, admin_password: str | None = None) -> dict[str, Any]:
    rng = random.Random(26024)
    now = datetime.now(UTC)
    today = now.date()
    pw = hash_password(DEMO_PASSWORD)

    await seed_regulations(session)
    regs = {r.code: r for r in (await session.execute(select(Regulation))).scalars().all()}

    subs: dict[str, Subsidiary] = {}
    for code, name, hq in SUBSIDIARIES:
        s = Subsidiary(code=code, name=name, headquarters=hq)
        session.add(s)
        subs[code] = s
    await session.flush()

    mines: list[tuple[Mine, float]] = []
    for code, name, sub, mtype, state, district, lat, lon, cap, workforce, risk in MINES:
        m = Mine(code=code, name=name, subsidiary_id=subs[sub].id, mine_type=mtype, state=state, district=district,
                 latitude=lat, longitude=lon, capacity_mtpa=cap, workforce=workforce,
                 boundary_geojson={"type": "Polygon", "coordinates": [[
                     [lon - 0.03, lat - 0.025], [lon + 0.03, lat - 0.025], [lon + 0.03, lat + 0.025],
                     [lon - 0.03, lat + 0.025], [lon - 0.03, lat - 0.025]]]})
        # Older mines onboarded long ago; two onboarded this month for the KPI delta.
        m.created_at = now - timedelta(days=400 if code not in ("WCL-PDM", "ECL-JHJ") else 5)
        session.add(m)
        mines.append((m, risk))
    await session.flush()
    mine_by_code = {m.code: m for m, _ in mines}

    # ------------------------------------------------------------------ users
    users: dict[str, User] = {}

    def add_user(username: str, full_name: str, role: Role, *, email: str | None = None, mine: Mine | None = None,
                 sub: Subsidiary | None = None, designation: str | None = None, contractor: Contractor | None = None,
                 password_hash: str | None = None) -> User:
        u = User(username=username, email=email or f"{username}@coalminegov.example", full_name=full_name, role=role,
                 status=UserStatus.ACTIVE, password_hash=password_hash or pw, mine_id=mine.id if mine else None,
                 subsidiary_id=(mine.subsidiary_id if mine else sub.id if sub else None), designation=designation,
                 contractor_id=contractor.id if contractor else None, phone=f"+9198{rng.randint(10000000, 99999999)}",
                 password_changed_at=now)
        session.add(u)
        users[username] = u
        return u

    add_user("admin", "System Administrator", Role.ADMIN, designation="Platform Administrator",
             password_hash=hash_password(admin_password) if admin_password else None)
    add_user("ravi.kumar", "Ravi Kumar", Role.MINE_OFFICIAL, mine=mine_by_code["MCL-KLG"], designation="Mine Manager")
    add_user("anita.sharma", "Anita Sharma", Role.CORPORATE, designation="GM (Safety), CIL HQ")
    add_user("suresh.patnaik", "Suresh Patnaik", Role.CORPORATE, sub=subs["MCL"], designation="Chief GM (Safety), MCL")
    add_user("dgms.regulator", "DGMS Regulator", Role.REGULATOR, email="regulator@coalminegov.example",
             designation="Deputy Director of Mines Safety")
    for i, (m, _) in enumerate(mines):
        if m.code == "MCL-KLG":
            continue
        name = f"{FIRST[i % len(FIRST)]} {LAST[(i * 3) % len(LAST)]}"
        add_user(f"mgr.{m.code.lower()}", name, Role.MINE_OFFICIAL, mine=m, designation="Mine Manager")
    await session.flush()

    # ------------------------------------------------------------ contractors
    contractors: list[Contractor] = []
    state_codes = {"MCL": "21", "SECL": "22", "NCL": "23", "CCL": "20", "BCCL": "20", "ECL": "19", "WCL": "27"}
    for i, (name, sub, category) in enumerate(CONTRACTORS):
        gstin = _gstin(rng, state_codes[sub])
        c = Contractor(subsidiary_id=subs[sub].id, name=name, registration_no=f"CLRA/{sub}/{2021 + i % 4}/{1000 + i}",
                       gstin=gstin, pan=gstin[2:12], category=category, contact_person=f"{FIRST[i]} {LAST[i % len(LAST)]}",
                       contact_email=f"compliance@{name.split()[0].lower()}.example.in",
                       contact_phone=f"+9194{rng.randint(10000000, 99999999)}", address=f"{subs[sub].headquarters}",
                       status=ContractorStatus.ACTIVE if i != 8 else ContractorStatus.PENDING_VERIFICATION,
                       verified=i != 8)
        session.add(c)
        contractors.append(c)
    await session.flush()
    contracts_by_mine: dict[uuid.UUID, list[Contractor]] = {}
    for i, c in enumerate(contractors):
        sub_mines = [m for m, _ in mines if m.subsidiary_id == c.subsidiary_id]
        for j, m in enumerate(rng.sample(sub_mines, k=min(2, len(sub_mines)))):
            session.add(Contract(contractor_id=c.id, mine_id=m.id, work_order_no=f"WO/{m.code}/{2025}/{100 + i * 3 + j}",
                                 title=f"{c.category} at {m.name}", value_inr=rng.randint(20, 900) * 1_000_000,
                                 start_date=today - timedelta(days=rng.randint(60, 500)),
                                 end_date=today + timedelta(days=rng.randint(90, 900)),
                                 workforce_count=rng.randint(40, 400), status=ContractStatus.ACTIVE))
            contracts_by_mine.setdefault(m.id, []).append(c)
    add_user("contractor.demo", "Mahanadi Earthmovers (Site In-charge)", Role.CONTRACTOR,
             sub=subs["MCL"], contractor=contractors[0], designation="Site In-charge")
    await session.flush()

    # ------------------------------------------------------------- compliance
    open_items: list[ComplianceItem] = []
    for m, risk in mines:
        officer = next(u for u in users.values() if u.mine_id == m.id)
        for cat, title, reg_code, freq in COMPLIANCE_TEMPLATES:
            reg = regs.get(reg_code)
            roll = rng.random()
            if roll < 0.55:
                due = today + timedelta(days=rng.randint(3, 120))
                status, done = ComplianceStatus.DUE, today - timedelta(days=rng.randint(5, 40))
            elif roll < 0.55 + 0.25:
                due = today + timedelta(days=rng.randint(15, 180))
                status, done = ComplianceStatus.COMPLIANT, today - timedelta(days=rng.randint(1, 20))
            elif roll < 0.8 + 0.1:
                due = today + timedelta(days=rng.randint(2, 30))
                status, done = ComplianceStatus.IN_PROGRESS, None
            else:
                due = today - timedelta(days=rng.randint(2, 45)) if rng.random() < 0.3 + risk * 0.6 else today + timedelta(days=10)
                status = ComplianceStatus.OVERDUE if due < today else ComplianceStatus.DUE
                done = None
            item = ComplianceItem(
                mine_id=m.id, category=cat, title=title, regulation_id=reg.id if reg else None,
                regulation_ref=f"{reg.act} — {reg.section}" if reg else None, frequency=freq, due_date=due,
                status=status, owner_id=officer.id,
                last_completed_at=datetime.combine(done, time(10), tzinfo=UTC) if done else None,
                last_completed_by=officer.id if done else None, created_by=officer.id,
            )
            session.add(item)
            if status != ComplianceStatus.COMPLIANT:
                open_items.append(item)
    await session.flush()

    # ------------------------------------------------ inspections & violations
    open_violations: list[Violation] = []
    inspection_rows = 0
    violation_rows = 0
    for m, risk in mines:
        officer = next(u for u in users.values() if u.mine_id == m.id)
        mine_contractors = contracts_by_mine.get(m.id, [])
        # Risky mines show an upward trend in the last months (drives trend chart + model labels).
        for day_offset in range(365, 0, -1):
            at_day = today - timedelta(days=day_offset)
            if rng.random() > 0.085:
                continue
            recency = 1.0 + (0.6 * risk if day_offset < 120 else 0.0)
            itype = rng.choice([InspectionType.ROUTINE, InspectionType.ROUTINE, InspectionType.SAFETY,
                                InspectionType.ENVIRONMENTAL, InspectionType.COMPLIANCE_AUDIT])
            checklist = []
            fails = 0
            for item in rng.sample(CHECKLIST, k=6):
                passed = rng.random() > risk * 0.35 * recency
                fails += 0 if passed else 1
                checklist.append({"item": item, "passed": passed, "note": None if passed else "Deficiency observed; see findings"})
            outcome = (InspectionOutcome.COMPLIANT if fails == 0 else
                       InspectionOutcome.MINOR_ISSUES if fails == 1 else InspectionOutcome.NON_COMPLIANT)
            at = datetime.combine(at_day, time(rng.randint(3, 11), rng.randint(0, 59)), tzinfo=UTC)
            lat = m.latitude + rng.uniform(-0.01, 0.01)
            lon = m.longitude + rng.uniform(-0.01, 0.01)
            insp = Inspection(
                mine_id=m.id, inspector_id=officer.id, inspection_type=itype,
                title=f"{itype.value.replace('_', ' ').title()} inspection — {m.name}",
                notes=f"{itype.value.replace('_', ' ').title()} inspection covering pit, haul roads, CHP and statutory records.",
                checklist=checklist, latitude=lat, longitude=lon, geo_accuracy_m=rng.uniform(4, 25),
                distance_from_mine_km=round(rng.uniform(0.1, 1.5), 2), geo_verified=True, inspected_at=at,
                status=InspectionStatus.REVIEWED if day_offset > 7 else InspectionStatus.SUBMITTED,
                outcome=outcome, source=rng.choice(["web", "mobile", "mobile"]),
            )
            session.add(insp)
            await session.flush()
            inspection_rows += 1
            for _ in range(fails if outcome == InspectionOutcome.NON_COMPLIANT else (1 if fails and rng.random() < 0.5 else 0)):
                cat, sev, title, desc, ref = rng.choice(VIOLATION_TEMPLATES)
                if sev == Severity.CRITICAL and rng.random() > risk:
                    sev = Severity.HIGH
                contractor = rng.choice(mine_contractors) if mine_contractors and rng.random() < 0.45 else None
                age = day_offset
                closed = age > 25 and rng.random() < 0.93 - risk * 0.2
                v = Violation(
                    mine_id=m.id, inspection_id=insp.id, contractor_id=contractor.id if contractor else None,
                    kind=ViolationKind.VIOLATION, category=cat, title=title, description=desc, severity=sev,
                    severity_confirmed=True, ai_suggested_severity=sev, ai_confidence=round(rng.uniform(0.6, 0.92), 2),
                    ai_rationale="Historical record (baseline import).", ai_source="rules", detected_by=DetectedBy.HUMAN,
                    regulation_ref=ref, latitude=lat, longitude=lon, occurred_at=at, reported_by=officer.id,
                    confirmed_by=officer.id,
                    status=ViolationStatus.CLOSED if closed else rng.choice([ViolationStatus.OPEN, ViolationStatus.ACTION_ASSIGNED,
                                                                             ViolationStatus.PENDING_VERIFICATION]),
                    escalation_level=0 if closed else rng.choice([0, 0, 1, 2]) if age > 7 else 0,
                    closed_at=at + timedelta(days=rng.randint(3, 20)) if closed else None,
                )
                session.add(v)
                await session.flush()
                v.workflow_id = f"violation-escalation-{v.id}"
                violation_rows += 1
                if v.status != ViolationStatus.OPEN:
                    assignee = officer
                    deadline = at + timedelta(days=rng.randint(5, 21))
                    if closed:
                        a_status = ActionStatus.VERIFIED
                    elif v.status == ViolationStatus.PENDING_VERIFICATION:
                        a_status = ActionStatus.SUBMITTED
                    else:
                        a_status = ActionStatus.OVERDUE if deadline < now else ActionStatus.IN_PROGRESS
                    session.add(CorrectiveAction(
                        violation_id=v.id, title=f"Rectify: {title}",
                        description="Rectify the deficiency, record evidence and brief the shift crew.",
                        assigned_to=assignee.id, assigned_by=officer.id, deadline=deadline, status=a_status,
                        completion_notes="Rectified and verified on site." if a_status in (ActionStatus.VERIFIED, ActionStatus.SUBMITTED) else None,
                        submitted_at=deadline - timedelta(days=1) if a_status in (ActionStatus.VERIFIED, ActionStatus.SUBMITTED) else None,
                        verified_by=users["suresh.patnaik"].id if a_status == ActionStatus.VERIFIED else None,
                        verified_at=v.closed_at if a_status == ActionStatus.VERIFIED else None,
                        verification_notes="Verified during follow-up inspection." if a_status == ActionStatus.VERIFIED else None,
                    ))
                if not closed:
                    open_violations.append(v)
    await session.flush()

    # ------------------------------------------------------------- attendance
    rows: list[dict[str, Any]] = []
    for m, _risk in mines:
        officer = next(u for u in users.values() if u.mine_id == m.id)
        mine_contractors = contracts_by_mine.get(m.id, [])
        for d in range(1, 91):
            day = today - timedelta(days=d)
            for _ in range(rng.randint(6, 16)):
                rows.append({
                    "id": uuid.uuid4(), "mine_id": m.id, "recorded_by": officer.id,
                    "contractor_id": rng.choice(mine_contractors).id if mine_contractors and rng.random() < 0.6 else None,
                    "worker_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                    "shift": rng.choice([Shift.A, Shift.B, Shift.C]),
                    "check_in_at": datetime.combine(day, time(rng.choice([0, 8, 16]), rng.randint(0, 40)), tzinfo=UTC),
                    "latitude": m.latitude + rng.uniform(-0.005, 0.005),
                    "longitude": m.longitude + rng.uniform(-0.005, 0.005),
                    "geo_verified": True, "source": "mobile",
                    "created_at": now, "updated_at": now,
                })
    for start in range(0, len(rows), 2000):
        await session.execute(insert(AttendanceRecord), rows[start:start + 2000])

    # ---------------------------------------------------------------- events
    # Emit events for *open* work so Temporal starts reminder/escalation workflows and
    # the audit chain records the baseline. Historical closed items stay as imported data.
    record_event(session, "system.seeded", entity_type="system", entity_id="demo-seed", actor=None,
                 data={"mines": len(mines), "inspections": inspection_rows, "violations": violation_rows,
                       "seeded": True})
    for item in open_items:
        record_event(session, "compliance.created", entity_type="compliance_item", entity_id=item.id, actor=None,
                     mine_id=item.mine_id, after={"title": item.title, "due_date": item.due_date.isoformat(),
                                                  "status": item.status.value}, data={"seeded": True})
    for v in open_violations:
        record_event(session, "violation.flagged", entity_type="violation", entity_id=v.id, actor=None,
                     mine_id=v.mine_id, after=snapshot(v, V_FIELDS),
                     data={"severity": v.severity.value, "kind": v.kind.value, "category": v.category.value,
                           "seeded": True})
    await session.commit()
    return {
        "subsidiaries": len(subs), "mines": len(mines), "users": len(users), "contractors": len(contractors),
        "compliance_items": len(COMPLIANCE_TEMPLATES) * len(mines), "inspections": inspection_rows,
        "violations": violation_rows, "open_violations": len(open_violations), "attendance_records": len(rows),
        "demo_password": DEMO_PASSWORD,
    }
