"""Unit tests for pure domain logic (no external services)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.ai import anomaly, classifier, risk
from app.ai.vectorstore import chunk_text, point_id, tenant_filter
from app.core import crypto, security
from app.models.enums import Frequency, Severity
from app.services import geo
from app.services.audit import GENESIS_HASH, hash_payload
from app.services.compliance import add_months, next_due_date
from app.services.media import UploadRejected, sniff


# ------------------------------------------------------------------ security
def test_password_hash_and_verify() -> None:
    h = security.hash_password("Str0ng!Passw0rd")
    assert security.verify_password("Str0ng!Passw0rd", h)
    assert not security.verify_password("wrong", h)
    assert not security.verify_password("anything", None)


def test_password_strength_rules() -> None:
    assert security.validate_password_strength("Str0ng!Passw0rd") == []
    problems = security.validate_password_strength("weak")
    assert len(problems) >= 3


def test_access_token_roundtrip_and_type_check() -> None:
    token, _ = security.create_access_token("user-1", "admin")
    claims = security.decode_access_token(token)
    assert claims["sub"] == "user-1" and claims["role"] == "admin"
    with pytest.raises(security.TokenError):
        security.decode_access_token(token + "tampered")


# -------------------------------------------------------------------- crypto
def test_pii_encryption_roundtrip() -> None:
    token = crypto.encrypt_str("ABCDE1234F")
    assert token != "ABCDE1234F"
    assert crypto.decrypt_str(token) == "ABCDE1234F"


def test_hash_chain_detects_tampering() -> None:
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    p1 = hash_payload(event_id="e1", entity_type="violation", entity_id="1", action="violation.flagged",
                      actor_id=None, before=None, after={"severity": "high"}, ts=ts)
    h1 = crypto.chain_hash(GENESIS_HASH, p1)
    p2 = hash_payload(event_id="e2", entity_type="violation", entity_id="1", action="violation.closed",
                      actor_id=None, before={"severity": "high"}, after=None, ts=ts)
    h2 = crypto.chain_hash(h1, p2)
    tampered = {**p1, "after": {"severity": "low"}}
    assert crypto.chain_hash(GENESIS_HASH, tampered) != h1
    assert crypto.chain_hash(crypto.chain_hash(GENESIS_HASH, tampered), p2) != h2
    # canonical JSON is key-order independent
    assert crypto.canonical_json({"b": 1, "a": 2}) == crypto.canonical_json({"a": 2, "b": 1})


# ----------------------------------------------------------------------- geo
def test_haversine_and_geofence() -> None:
    # Talcher → Angul ≈ 15 km
    d = geo.haversine_km(20.955, 85.135, 20.84, 85.10)
    assert 12 < d < 15
    ok, dist = geo.verify_location(20.956, 85.136, 20.955, 85.135, None, 15)
    assert ok and dist is not None and dist < 1
    far, _ = geo.verify_location(22.33, 82.60, 20.955, 85.135, None, 15)
    assert not far
    poly = {"type": "Polygon", "coordinates": [[[85.0, 20.9], [85.2, 20.9], [85.2, 21.0], [85.0, 21.0], [85.0, 20.9]]]}
    inside, _ = geo.verify_location(20.95, 85.1, 22.0, 86.0, poly, 1)
    assert inside  # inside the lease polygon even though far from centroid
    assert geo.verify_location(None, None, 20.9, 85.1, None, 15) == (False, None)


# ---------------------------------------------------------------- compliance
def test_add_months_clamps_day() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)


def test_next_due_date_rolls_past_today() -> None:
    today = date(2026, 9, 23)
    assert next_due_date(date(2026, 9, 1), Frequency.MONTHLY, today) == date(2026, 10, 1)
    assert next_due_date(date(2026, 6, 30), Frequency.MONTHLY, today) == date(2026, 9, 30)
    assert next_due_date(date(2026, 9, 1), Frequency.ONE_TIME, today) is None


# ---------------------------------------------------------------- classifier
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Roof fall near the face; two workers trapped", Severity.CRITICAL),
        ("Dumper operating with brake failure on haul road", Severity.HIGH),
        ("Workers found without helmet and safety shoes", Severity.MEDIUM),
        ("Register not countersigned, minor documentation lapse", Severity.LOW),
    ],
)
def test_rules_classifier(text: str, expected: Severity) -> None:
    result = classifier.classify_rules(text, text)
    assert result.severity == expected
    assert result.source == "rules"
    assert 0 < result.confidence <= 0.85


def test_rules_classifier_matches_whole_words_only() -> None:
    result = classifier.classify_rules("Vehicle stopped", "Operator stopped the truck safely")
    assert "ppe" not in result.rationale and result.severity == Severity.MEDIUM


def test_rules_classifier_defaults_to_medium() -> None:
    assert classifier.classify_rules("Something odd", "Unclear observation").severity == Severity.MEDIUM


# ---------------------------------------------------------------------- risk
def _history(n_critical: int, open_: int) -> risk.EntityHistory:
    now = datetime.now(UTC)
    h = risk.EntityHistory()
    for i in range(n_critical):
        h.violations.append(risk.ViolationRow(now - timedelta(days=5 + i), "critical", "safety", None, 1))
    for i in range(open_):
        h.violations.append(risk.ViolationRow(now - timedelta(days=20 + i), "medium", "environment", None))
    h.inspections.append(risk.InspectionRow(now - timedelta(days=3), "non_compliant"))
    return h


def test_risk_features_and_expert_score_monotonic() -> None:
    now = datetime.now(UTC)
    low = risk.compute_features(_history(0, 1), now)
    high = risk.compute_features(_history(3, 6), now)
    assert high["critical_90d"] == 3 and high["open_violations"] == 9
    s_low, _ = risk.expert_score(low)
    s_high, explanation = risk.expert_score(high)
    assert s_high > s_low
    assert explanation["drivers"][0]["feature"] == "critical_90d"
    assert risk.band(s_high) in ("high", "critical")


def test_risk_features_are_point_in_time() -> None:
    now = datetime.now(UTC)
    h = _history(2, 0)
    past = risk.compute_features(h, now - timedelta(days=30))
    assert past["critical_90d"] == 0  # violations after the snapshot must not leak into features


def test_model_training_requires_both_classes() -> None:
    import numpy as np

    x = np.zeros((50, len(risk.FEATURES)))
    y = np.zeros(50, dtype=int)
    assert risk.train(x, y) is None


# ------------------------------------------------------------------- anomaly
def test_poisson_tail() -> None:
    assert anomaly.poisson_sf(0, 3) == 1.0
    assert anomaly.poisson_sf(10, 1) < 1e-6


def test_recurring_violation_detection() -> None:
    now = datetime.now(UTC)
    occ = [(now - timedelta(days=d), "safety") for d in (1, 3, 5, 8, 12)]
    occ += [(now - timedelta(days=100), "environment")]
    findings = anomaly.recurring_violations(occ, now=now, mine_label="Test Mine", mine_id="m1",
                                            threshold=3, window_days=30)
    assert len(findings) == 1 and findings[0].metric["category"] == "safety"


def test_attendance_drop() -> None:
    today = date(2026, 9, 23)
    daily = {today - timedelta(days=i): (30 if i > 7 else 5) for i in range(1, 40)}
    findings = anomaly.attendance_drop(daily, today=today, mine_label="M", mine_id="m1")
    assert findings and findings[0].kind == "attendance_drop"


# --------------------------------------------------------------- vectorstore
def test_chunking_and_ids() -> None:
    text = "\n\n".join(f"Paragraph {i} " + "x" * 300 for i in range(10))
    chunks = chunk_text(text, max_chars=1000, overlap=100)
    assert len(chunks) >= 3 and all(len(c) <= 1300 for c in chunks)
    assert point_id("regulation", "a", 0) == point_id("regulation", "a", 0)
    assert point_id("regulation", "a", 0) != point_id("regulation", "a", 1)


def test_tenant_filter_restricts_to_public_or_visible_mines() -> None:
    f = tenant_filter(["m1"], ["violation"])
    dumped = f.model_dump_json()
    assert "public" in dumped and "m1" in dumped and "violation" in dumped
    assert tenant_filter(None).must is None  # unrestricted principals


# --------------------------------------------------------------------- media
def test_magic_byte_sniffing() -> None:
    assert sniff(b"\xff\xd8\xff\xe0rest", "image/jpeg") == ("image/jpeg", "jpg")
    assert sniff(b"%PDF-1.7 ...", "application/octet-stream")[0] == "application/pdf"
    with pytest.raises(UploadRejected):
        sniff(b"MZ\x90\x00 executable", "image/png")
