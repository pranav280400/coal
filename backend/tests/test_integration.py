"""End-to-end API tests: auth, RBAC/tenancy, compliance, inspection → violation →
corrective action → verification, offline ingest idempotency, dashboards, and the
hash-chained audit trail built from outbox events."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.integration

PASSWORD = "Str0ng!Passw0rd#1"


async def _login(client: Any, username: str, password: str = PASSWORD) -> dict[str, str]:
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
async def world(app_client: Any) -> dict[str, Any]:
    """Admin bootstrapped in DB; everything else created through the API."""
    from app.core.db import session_scope
    from app.core.security import hash_password
    from app.models import User
    from app.models.enums import Role, UserStatus

    async with session_scope() as s:
        s.add(User(username="root", email="root@test.example", full_name="Root Admin", role=Role.ADMIN,
                   status=UserStatus.ACTIVE, password_hash=hash_password(PASSWORD)))
    admin = await _login(app_client, "root")
    sub = (await app_client.post("/api/v1/subsidiaries", headers=admin,
                                 json={"code": "TST", "name": "Test Coalfields Ltd"})).json()
    mines = []
    for code, lat, lon in (("TST-A", 21.0, 85.0), ("TST-B", 23.0, 86.0)):
        r = await app_client.post("/api/v1/mines", headers=admin, json={
            "subsidiary_id": sub["id"], "code": code, "name": f"Mine {code}", "state": "Odisha",
            "latitude": lat, "longitude": lon})
        assert r.status_code == 201, r.text
        mines.append(r.json())
    users = {}
    for username, role, mine in (("official.a", "mine_official", mines[0]), ("official.a2", "mine_official", mines[0]),
                                 ("official.b", "mine_official", mines[1]), ("regulator", "regulator", None)):
        r = await app_client.post("/api/v1/users", headers=admin, json={
            "username": username, "email": f"{username}@test.example", "full_name": username.title(),
            "password": PASSWORD, "role": role, "mine_id": mine["id"] if mine else None})
        assert r.status_code == 201, r.text
        users[username] = r.json()
    return {"admin": admin, "sub": sub, "mines": mines, "users": users}


async def test_health_and_auth_errors(app_client: Any) -> None:
    assert (await app_client.get("/health/live")).status_code == 200
    r = await app_client.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/problem+json")
    r = await app_client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401


async def test_login_me_refresh_rotation(app_client: Any, world: dict[str, Any]) -> None:
    r = await app_client.post("/api/v1/auth/login", json={"username": "official.a", "password": PASSWORD})
    tokens = r.json()
    me = await app_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200 and me.json()["role"] == "mine_official"
    assert "inspection:write" in me.json()["permissions"]
    r1 = await app_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200
    # Within the reuse interval a concurrent replay receives the same rotated pair.
    r_race = await app_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r_race.status_code == 200 and r_race.json()["refresh_token"] == r1.json()["refresh_token"]
    # After the interval, replaying the rotated token is theft: rejected and the family is revoked.
    from app.api.v1.auth import _grace_key
    from app.core.redis import get_redis

    await get_redis().delete(_grace_key(tokens["refresh_token"]))
    r2 = await app_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401
    r3 = await app_client.post("/api/v1/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]})
    assert r3.status_code == 401


async def test_access_request_requires_approval(app_client: Any, world: dict[str, Any]) -> None:
    r = await app_client.post("/api/v1/auth/register", json={
        "username": "newbie", "email": "newbie@test.example", "full_name": "New Bie", "password": PASSWORD,
        "requested_role": "mine_official", "mine_code": "TST-A"})
    assert r.status_code == 202
    r = await app_client.post("/api/v1/auth/login", json={"username": "newbie", "password": PASSWORD})
    assert r.status_code == 403
    weak = await app_client.post("/api/v1/auth/register", json={
        "username": "weakling", "email": "weak@test.example", "full_name": "Weak", "password": "password123",
        "requested_role": "mine_official"})
    assert weak.status_code == 422


async def test_tenant_isolation_and_regulator_read_only(app_client: Any, world: dict[str, Any]) -> None:
    a = await _login(app_client, "official.a")
    b = await _login(app_client, "official.b")
    reg = await _login(app_client, "regulator")
    mine_a, mine_b = world["mines"]
    r = await app_client.post("/api/v1/compliance", headers=a, json={
        "mine_id": mine_a["id"], "category": "safety", "title": "Isolation probe item",
        "due_date": (date.today() + timedelta(days=10)).isoformat()})
    assert r.status_code == 201
    item_id = r.json()["id"]
    assert (await app_client.get(f"/api/v1/compliance/{item_id}", headers=b)).status_code == 404
    listed = (await app_client.get("/api/v1/mines", headers=b)).json()
    assert [m["code"] for m in listed["items"]] == ["TST-B"]
    # official B cannot write to mine A
    r = await app_client.post("/api/v1/compliance", headers=b, json={
        "mine_id": mine_a["id"], "category": "safety", "title": "Cross-tenant write",
        "due_date": date.today().isoformat()})
    assert r.status_code == 403
    # regulator reads everything but cannot write
    assert (await app_client.get(f"/api/v1/compliance/{item_id}", headers=reg)).status_code == 200
    r = await app_client.post("/api/v1/compliance", headers=reg, json={
        "mine_id": mine_a["id"], "category": "safety", "title": "Regulator write", "due_date": date.today().isoformat()})
    assert r.status_code == 403


async def test_compliance_recurring_completion_rolls_forward(app_client: Any, world: dict[str, Any]) -> None:
    a = await _login(app_client, "official.a")
    due = date.today() - timedelta(days=2)
    r = await app_client.post("/api/v1/compliance", headers=a, json={
        "mine_id": world["mines"][0]["id"], "category": "environment", "title": "Monthly water quality report",
        "frequency": "monthly", "due_date": due.isoformat()})
    item = r.json()
    assert item["status"] == "overdue"
    r = await app_client.post(f"/api/v1/compliance/{item['id']}/complete", headers=a,
                              json={"notes": "Report submitted to SPCB"})
    done = r.json()
    assert r.status_code == 200 and done["status"] == "due"
    assert date.fromisoformat(done["due_date"]) > date.today()
    summary = (await app_client.get("/api/v1/compliance/summary", headers=a)).json()
    assert summary["total"] >= 2 and "overview" in summary


async def test_inspection_violation_action_lifecycle(app_client: Any, world: dict[str, Any]) -> None:
    a = await _login(app_client, "official.a")
    a2 = await _login(app_client, "official.a2")
    mine_a = world["mines"][0]
    # Geo-tag ~300 km away from the mine → recorded but flagged as not verified.
    r = await app_client.post("/api/v1/inspections", headers=a, json={
        "mine_id": mine_a["id"], "inspection_type": "safety", "title": "Pit safety round",
        "checklist": [{"item": "Berms", "passed": False, "note": "Low berm"}, {"item": "PPE", "passed": True}],
        "geo": {"latitude": 23.5, "longitude": 86.5, "accuracy_m": 8}})
    assert r.status_code == 201, r.text
    insp = r.json()
    assert insp["geo_verified"] is False and insp["distance_from_mine_km"] > 100
    assert insp["outcome"] == "non_compliant"

    # Photo evidence (magic bytes validated).
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 2048
    r = await app_client.post(f"/api/v1/media/inspection/{insp['id']}", headers=a,
                              files={"file": ("berm.jpg", jpeg, "image/jpeg")},
                              data={"latitude": "21.0", "longitude": "85.0"})
    assert r.status_code == 201, r.text
    r = await app_client.post(f"/api/v1/media/inspection/{insp['id']}", headers=a,
                              files={"file": ("evil.jpg", b"MZ\x90\x00binary", "image/jpeg")})
    assert r.status_code == 415

    # Violation without severity → AI (rules fallback, LLM unreachable) suggests one, unconfirmed.
    r = await app_client.post("/api/v1/violations", headers=a, json={
        "mine_id": mine_a["id"], "inspection_id": insp["id"], "category": "safety",
        "title": "Dumper brake failure on haul road",
        "description": "Rear dump truck operating with brake failure near the ramp; no reversing alarm."})
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["ai_suggested_severity"] == "high" and v["ai_source"] == "rules" and v["severity_confirmed"] is False

    r = await app_client.post(f"/api/v1/violations/{v['id']}/confirm", headers=a,
                              json={"severity": "critical", "notes": "Upgraded after site review"})
    assert r.json()["severity"] == "critical" and r.json()["severity_confirmed"]

    # High/critical cannot be closed without verified actions.
    r = await app_client.post(f"/api/v1/violations/{v['id']}/close", headers=a, json={"notes": "closing"})
    r2 = await app_client.post("/api/v1/corrective-actions", headers=a, json={
        "violation_id": v["id"], "title": "Repair brakes and fit alarm", "assigned_to": world["users"]["official.a2"]["id"],
        "deadline": (datetime.now(UTC) + timedelta(days=3)).isoformat()})
    assert r.status_code == 422
    assert r2.status_code == 201, r2.text
    action = r2.json()
    assert (await app_client.get(f"/api/v1/violations/{v['id']}", headers=a)).json()["status"] == "action_assigned"

    r = await app_client.post(f"/api/v1/corrective-actions/{action['id']}/submit", headers=a2,
                              json={"completion_notes": "Brakes overhauled; alarm installed and tested."})
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    # Segregation of duties: the assignee cannot verify their own work.
    r = await app_client.post(f"/api/v1/corrective-actions/{action['id']}/verify", headers=a2,
                              json={"decision": "approve", "notes": "self-approve"})
    assert r.status_code == 403
    r = await app_client.post(f"/api/v1/corrective-actions/{action['id']}/verify", headers=a,
                              json={"decision": "approve", "notes": "Verified on site"})
    assert r.status_code == 200 and r.json()["status"] == "verified"
    final = (await app_client.get(f"/api/v1/violations/{v['id']}", headers=a)).json()
    assert final["status"] == "closed" and final["closed_at"]

    signals = [s[1] for s in app_client.signals if s[0] == f"violation-escalation-{v['id']}"]
    assert signals == ["severity_changed", "action_assigned", "action_submitted", "action_verified"]

    detail = (await app_client.get(f"/api/v1/inspections/{insp['id']}", headers=a)).json()
    assert len(detail["media"]) == 1 and len(detail["violations"]) == 1


async def test_offline_ingest_is_idempotent(app_client: Any, world: dict[str, Any]) -> None:
    a = await _login(app_client, "official.a")
    cid = uuid.uuid4().hex
    batch = {"device_id": "android-test-01", "events": [
        {"client_event_id": cid, "event_type": "attendance.logged", "captured_at": datetime.now(UTC).isoformat(),
         "payload": {"mine_id": world["mines"][0]["id"], "worker_name": "Ramesh Soren", "shift": "A",
                     "geo": {"latitude": 21.001, "longitude": 85.001}}},
        {"client_event_id": uuid.uuid4().hex, "event_type": "attendance.logged",
         "captured_at": datetime.now(UTC).isoformat(),
         "payload": {"mine_id": world["mines"][1]["id"], "worker_name": "Wrong Mine", "shift": "B"}},
    ]}
    r = await app_client.post("/api/v1/ingest/events", headers=a, json=batch)
    results = r.json()["results"]
    assert r.status_code == 202 and results[0]["status"] == "accepted" and results[1]["status"] == "rejected"
    replay = await app_client.post("/api/v1/ingest/events", headers=a, json={**batch, "events": batch["events"][:1]})
    assert replay.json()["results"][0]["status"] == "duplicate"
    status = await app_client.get("/api/v1/ingest/status", headers=a, params={"ids": [cid]})
    assert status.json()[cid]["entity_type"] == "attendance"


async def test_dashboard_and_search(app_client: Any, world: dict[str, Any]) -> None:
    a = await _login(app_client, "official.a")
    dash = (await app_client.get("/api/v1/dashboard/summary", headers=a, params={"fresh": True})).json()
    assert dash["kpis"]["total_mines"] == 1 and dash["kpis"]["inspections"] >= 1
    assert len(dash["violation_trends"]) == 6 and dash["mine_locations"][0]["code"] == "TST-A"
    cached = (await app_client.get("/api/v1/dashboard/summary", headers=a)).json()
    assert cached["cached"] is True
    admin_dash = (await app_client.get("/api/v1/dashboard/summary", headers=world["admin"], params={"fresh": True})).json()
    assert admin_dash["kpis"]["total_mines"] == 2
    found = (await app_client.get("/api/v1/search", headers=a, params={"q": "brake"})).json()
    assert found["violations"]


async def test_audit_chain_from_outbox(app_client: Any, world: dict[str, Any]) -> None:
    """Replays outbox events through the audit consumer handler, verifies, then detects tampering."""
    from app.consumers.handlers import handle_audit
    from app.core.db import session_scope
    from app.models import OutboxEvent

    async with session_scope() as s:
        events = (await s.execute(select(OutboxEvent).order_by(OutboxEvent.id))).scalars().all()
        payloads = [e.payload for e in events]
    assert any(p["event_type"] == "violation.closed" for p in payloads)
    for p in payloads + payloads[:3]:  # duplicates must be ignored
        async with session_scope() as s:
            await handle_audit(s, p)
    reg = await _login(app_client, "regulator")
    ok = (await app_client.get("/api/v1/audit/verify", headers=reg)).json()
    assert ok["valid"] is True and ok["checked"] == len(payloads)
    official = await _login(app_client, "official.a")
    assert (await app_client.get("/api/v1/audit/verify", headers=official)).status_code == 403

    async with session_scope() as s:
        with pytest.raises(Exception, match="append-only"):
            await s.execute(text("UPDATE audit_log SET action = 'forged' WHERE id = (SELECT min(id) FROM audit_log)"))
    # Simulate a privileged attacker bypassing the trigger: the chain must detect it.
    async with session_scope() as s:
        await s.execute(text("ALTER TABLE audit_log DISABLE TRIGGER trg_audit_log_no_update_delete"))
        await s.execute(text("UPDATE audit_log SET after = '{\"forged\": true}' WHERE id = (SELECT min(id) + 2 FROM audit_log)"))
        await s.execute(text("ALTER TABLE audit_log ENABLE TRIGGER trg_audit_log_no_update_delete"))
    bad = (await app_client.get("/api/v1/audit/verify", headers=reg)).json()
    assert bad["valid"] is False and bad["first_invalid_id"] is not None


async def test_notifications_fanout(app_client: Any, world: dict[str, Any]) -> None:
    """Notification consumer turns an action.assigned event into an in-app notification."""
    from app.consumers.handlers import handle_notifications
    from app.core.db import session_scope
    from app.models import OutboxEvent

    async with session_scope() as s:
        ev = (await s.execute(select(OutboxEvent).where(
            OutboxEvent.payload["event_type"].astext == "action.assigned"))).scalars().first()
        payload = ev.payload
    async with session_scope() as s:
        await handle_notifications(s, payload)
    a2 = await _login(app_client, "official.a2")
    notes = (await app_client.get("/api/v1/notifications", headers=a2)).json()
    assert notes["unread"] >= 1 and notes["items"][0]["category"] == "action"
    r = await app_client.post("/api/v1/notifications/read", headers=a2, json={})
    assert r.status_code == 200
    assert (await app_client.get("/api/v1/notifications", headers=a2)).json()["unread"] == 0


async def test_rate_limit_headers(app_client: Any, world: dict[str, Any]) -> None:
    a = await _login(app_client, "official.a")
    r = await app_client.get("/api/v1/mines", headers=a)
    assert "X-RateLimit-Remaining" in r.headers and r.headers["X-Content-Type-Options"] == "nosniff"


async def test_auth_rate_limiter_blocks_bursts(app_client: Any) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.rate_limit_auth_per_minute
    settings.rate_limit_auth_per_minute = 2
    try:
        codes = [
            (await app_client.post("/api/v1/auth/forgot-password", json={"email": "x@test.example"},
                                   headers={"X-Forwarded-For": "203.0.113.77"})).status_code
            for _ in range(4)
        ]
    finally:
        settings.rate_limit_auth_per_minute = original
    assert codes[:2] == [202, 202] and codes[-1] == 429
