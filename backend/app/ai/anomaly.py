"""Anomaly detection (FR8): recurring violation patterns and operational outliers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
from sklearn.ensemble import IsolationForest


@dataclass(slots=True)
class Finding:
    kind: str
    fingerprint: str
    title: str
    description: str
    metric: dict
    score: float


def poisson_sf(k: int, lam: float) -> float:
    """P[X >= k] for X ~ Poisson(lam)."""
    if k <= 0:
        return 1.0
    term = math.exp(-lam)
    cdf = term
    for i in range(1, k):
        term *= lam / i
        cdf += term
    return max(0.0, 1.0 - cdf)


def recurring_violations(
    occurrences: list[tuple[datetime, str]],
    *,
    now: datetime,
    mine_label: str,
    mine_id: str,
    threshold: int,
    window_days: int,
    baseline_days: int = 180,
    alpha: float = 0.01,
) -> list[Finding]:
    """Flag categories whose recent count exceeds both an absolute threshold and
    what the mine's own baseline rate would plausibly produce (Poisson test)."""
    window_start = now - timedelta(days=window_days)
    base_start = window_start - timedelta(days=baseline_days)
    findings: list[Finding] = []
    categories = {c for _, c in occurrences}
    for cat in sorted(categories):
        recent = sum(1 for t, c in occurrences if c == cat and window_start < t <= now)
        prior = sum(1 for t, c in occurrences if c == cat and base_start < t <= window_start)
        if recent < threshold:
            continue
        expected = max(0.5, prior * window_days / baseline_days)
        p = poisson_sf(recent, expected)
        if p < alpha or recent >= 2 * threshold:
            score = round(min(10.0, -math.log10(max(p, 1e-10))), 2)
            findings.append(
                Finding(
                    kind="recurring_violation",
                    fingerprint=f"recurring:{mine_id}:{cat}:{now.date().isoformat()[:7]}",
                    title=f"Recurring {cat} violations at {mine_label}",
                    description=(
                        f"{recent} {cat} violations in the last {window_days} days versus an expected "
                        f"{expected:.1f} from the prior {baseline_days}-day baseline (p={p:.4f}). "
                        "Root-cause analysis and targeted inspection recommended."
                    ),
                    metric={"category": cat, "recent": recent, "expected": round(expected, 2), "p_value": p},
                    score=score,
                )
            )
    return findings


def operational_outliers(
    daily: dict[date, tuple[float, float, float, float]],
    *,
    mine_label: str,
    mine_id: str,
    recent_days: int = 7,
    contamination: float = 0.05,
) -> list[Finding]:
    """IsolationForest over daily vectors (inspections, violations, high+critical, attendance).

    Only recent days that are outliers *in the adverse direction* (more serious
    violations or collapsing attendance) are reported.
    """
    if len(daily) < 30:
        return []
    days = sorted(daily)
    x = np.array([daily[d] for d in days], dtype=float)
    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=7)
    model.fit(x)
    scores = model.decision_function(x)
    preds = model.predict(x)
    means = x.mean(axis=0)
    findings: list[Finding] = []
    for idx in range(max(0, len(days) - recent_days), len(days)):
        if preds[idx] != -1:
            continue
        insp, viol, serious, att = x[idx]
        adverse = serious > means[2] + 0.5 or viol > means[1] * 2 or (means[3] > 5 and att < means[3] * 0.5)
        if not adverse:
            continue
        d = days[idx]
        findings.append(
            Finding(
                kind="operational",
                fingerprint=f"operational:{mine_id}:{d.isoformat()}",
                title=f"Unusual operational pattern at {mine_label} on {d.isoformat()}",
                description=(
                    f"Daily profile deviates from the 90-day norm: {int(viol)} violations "
                    f"({int(serious)} high/critical) vs avg {means[1]:.1f}; attendance {int(att)} vs avg "
                    f"{means[3]:.0f}; inspections {int(insp)} vs avg {means[0]:.1f}."
                ),
                metric={
                    "date": d.isoformat(),
                    "violations": viol,
                    "serious": serious,
                    "attendance": att,
                    "inspections": insp,
                    "isolation_score": float(scores[idx]),
                },
                score=round(float(-scores[idx]) * 10, 2),
            )
        )
    return findings


def attendance_drop(
    daily_attendance: dict[date, int], *, today: date, mine_label: str, mine_id: str, drop_ratio: float = 0.4
) -> list[Finding]:
    last7 = [daily_attendance.get(today - timedelta(days=i), 0) for i in range(1, 8)]
    prior = [daily_attendance.get(today - timedelta(days=i), 0) for i in range(8, 36)]
    prior_avg = sum(prior) / len(prior)
    recent_avg = sum(last7) / len(last7)
    if prior_avg < 10 or recent_avg >= prior_avg * (1 - drop_ratio):
        return []
    drop = 1 - recent_avg / prior_avg
    return [
        Finding(
            kind="attendance_drop",
            fingerprint=f"attendance:{mine_id}:{today.isocalendar()[0]}-W{today.isocalendar()[1]}",
            title=f"Attendance drop at {mine_label}",
            description=(
                f"Average logged attendance fell {drop:.0%} (last 7 days {recent_avg:.0f}/day vs "
                f"{prior_avg:.0f}/day over the prior 4 weeks). Verify manpower deployment and field reporting."
            ),
            metric={"recent_avg": recent_avg, "prior_avg": prior_avg, "drop": drop},
            score=round(drop * 10, 2),
        )
    ]
