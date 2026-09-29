"""Compliance-risk scoring for mines and contractors (FR7).

Two tiers:

1. **Learned model** — a class-balanced logistic regression trained on monthly
   point-in-time snapshots of each mine's history, predicting whether a high or
   critical violation occurs in the following 30 days. It is retrained weekly by
   a Temporal schedule and versioned in ``ml_models``/object storage.
2. **Expert baseline** — a transparent weighted model used until enough labelled
   history exists (cold start) or for contractors.

Both return per-feature contributions so every score is explainable to officials.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURES: list[str] = [
    "critical_90d",
    "high_90d",
    "medium_90d",
    "low_90d",
    "weighted_365d",
    "open_violations",
    "overdue_actions",
    "overdue_compliance_ratio",
    "repeat_category_rate",
    "days_since_inspection",
    "noncompliant_inspection_ratio",
    "escalations_90d",
]

FEATURE_LABELS: dict[str, str] = {
    "critical_90d": "Critical violations (90 days)",
    "high_90d": "High-severity violations (90 days)",
    "medium_90d": "Medium violations (90 days)",
    "low_90d": "Low violations (90 days)",
    "weighted_365d": "Severity-weighted violations (1 year, decayed)",
    "open_violations": "Open violations",
    "overdue_actions": "Overdue corrective actions",
    "overdue_compliance_ratio": "Share of statutory items overdue",
    "repeat_category_rate": "Recurring violation categories",
    "days_since_inspection": "Days since last inspection",
    "noncompliant_inspection_ratio": "Non-compliant inspection ratio (180 days)",
    "escalations_90d": "Escalations (90 days)",
}

# Expert weights (per unit of feature) for the cold-start baseline.
EXPERT_WEIGHTS: dict[str, float] = {
    "critical_90d": 0.9,
    "high_90d": 0.35,
    "medium_90d": 0.08,
    "low_90d": 0.02,
    "weighted_365d": 0.01,
    "open_violations": 0.08,
    "overdue_actions": 0.25,
    "overdue_compliance_ratio": 1.6,
    "repeat_category_rate": 0.8,
    "days_since_inspection": 0.006,
    "noncompliant_inspection_ratio": 0.9,
    "escalations_90d": 0.15,
}

_SEV_WEIGHT = {"low": 1, "medium": 3, "high": 7, "critical": 15}
MIN_TRAINING_SAMPLES = 40
# A learned model only replaces the expert baseline if it demonstrably ranks risk well.
MIN_ACTIVATION_AUC = 0.65
# Calibrates the expert score so a typical mine (a few open items) lands in "moderate"
# and only mines with several severe/overdue signals reach "high"/"critical".
EXPERT_SCALE = 7.0


@dataclass(slots=True)
class ViolationRow:
    occurred_at: datetime
    severity: str
    category: str
    closed_at: datetime | None
    escalation_level: int = 0


@dataclass(slots=True)
class ActionRow:
    deadline: datetime
    submitted_at: datetime | None
    status: str


@dataclass(slots=True)
class ComplianceRow:
    due_date: date
    last_completed_at: datetime | None
    status: str


@dataclass(slots=True)
class InspectionRow:
    inspected_at: datetime
    outcome: str


@dataclass(slots=True)
class EntityHistory:
    violations: list[ViolationRow] = field(default_factory=list)
    actions: list[ActionRow] = field(default_factory=list)
    compliance: list[ComplianceRow] = field(default_factory=list)
    inspections: list[InspectionRow] = field(default_factory=list)


def compute_features(h: EntityHistory, at: datetime) -> dict[str, float]:
    """Point-in-time features as of ``at`` (only uses information known at ``at``)."""
    d90 = at - timedelta(days=90)
    d180 = at - timedelta(days=180)
    d365 = at - timedelta(days=365)
    past = [v for v in h.violations if v.occurred_at <= at]
    recent = [v for v in past if v.occurred_at > d90]
    counts = {s: sum(1 for v in recent if v.severity == s) for s in _SEV_WEIGHT}
    weighted = sum(
        _SEV_WEIGHT.get(v.severity, 1) * math.exp(-(at - v.occurred_at).days / 180)
        for v in past
        if v.occurred_at > d365
    )
    open_v = sum(1 for v in past if v.closed_at is None or v.closed_at > at)
    overdue_actions = sum(
        1 for a in h.actions if a.deadline < at and (a.submitted_at is None or a.submitted_at > at)
        and a.status not in ("verified",)
    )
    due_items = [c for c in h.compliance if c.due_date <= at.date() + timedelta(days=30)]
    overdue_items = [
        c for c in due_items
        if c.due_date < at.date() and (c.last_completed_at is None or c.last_completed_at > at)
        and c.status != "compliant"
    ]
    overdue_ratio = len(overdue_items) / len(due_items) if due_items else 0.0
    cat_counts: dict[str, int] = {}
    for v in recent:
        cat_counts[v.category] = cat_counts.get(v.category, 0) + 1
    repeat_rate = (
        sum(1 for c in cat_counts.values() if c >= 2) / len(cat_counts) if cat_counts else 0.0
    )
    past_insp = [i for i in h.inspections if i.inspected_at <= at]
    last_insp = max((i.inspected_at for i in past_insp), default=None)
    days_since = min(180.0, (at - last_insp).days) if last_insp else 180.0
    insp_180 = [i for i in past_insp if i.inspected_at > d180]
    nc_ratio = (
        sum(1 for i in insp_180 if i.outcome == "non_compliant") / len(insp_180) if insp_180 else 0.0
    )
    escalations = sum(v.escalation_level for v in recent)
    return {
        "critical_90d": float(counts["critical"]),
        "high_90d": float(counts["high"]),
        "medium_90d": float(counts["medium"]),
        "low_90d": float(counts["low"]),
        "weighted_365d": round(weighted, 3),
        "open_violations": float(open_v),
        "overdue_actions": float(overdue_actions),
        "overdue_compliance_ratio": round(overdue_ratio, 4),
        "repeat_category_rate": round(repeat_rate, 4),
        "days_since_inspection": float(days_since),
        "noncompliant_inspection_ratio": round(nc_ratio, 4),
        "escalations_90d": float(escalations),
    }


def band(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 35:
        return "moderate"
    return "low"


def _explain(contribs: dict[str, float], features: dict[str, float]) -> dict[str, Any]:
    top = sorted(contribs.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "features": features,
        "drivers": [
            {"feature": k, "label": FEATURE_LABELS[k], "value": features[k], "contribution": round(v, 4)}
            for k, v in top
            if v > 0
        ][:5],
    }


def expert_score(features: dict[str, float]) -> tuple[float, dict[str, Any]]:
    contribs = {k: EXPERT_WEIGHTS[k] * features[k] for k in FEATURES}
    z = sum(contribs.values())
    score = 100.0 * (1.0 - math.exp(-z / EXPERT_SCALE))
    return round(score, 1), _explain(contribs, features)


@dataclass(slots=True)
class TrainedModel:
    pipeline: Pipeline
    version: str
    metrics: dict[str, float]
    samples: int

    def score(self, features: dict[str, float]) -> tuple[float, dict[str, Any]]:
        x = np.array([[features[k] for k in FEATURES]])
        prob = float(self.pipeline.predict_proba(x)[0, 1])
        scaler: StandardScaler = self.pipeline.named_steps["scale"]
        clf: LogisticRegression = self.pipeline.named_steps["clf"]
        scaled = (x[0] - scaler.mean_) / np.where(scaler.scale_ == 0, 1, scaler.scale_)
        contribs = {k: float(c * v) for k, c, v in zip(FEATURES, clf.coef_[0], scaled, strict=True)}
        return round(prob * 100.0, 1), _explain(contribs, features)

    def dumps(self) -> bytes:
        buf = io.BytesIO()
        joblib.dump(self.pipeline, buf)
        return buf.getvalue()

    @classmethod
    def loads(cls, data: bytes, version: str, metrics: dict[str, float], samples: int) -> TrainedModel:
        return cls(joblib.load(io.BytesIO(data)), version, metrics, samples)


def build_training_set(
    histories: list[EntityHistory], *, months: int = 12, now: datetime | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Monthly snapshots; label = high/critical violation within the next 30 days."""
    now = now or datetime.now(UTC)
    xs: list[list[float]] = []
    ys: list[int] = []
    for h in histories:
        for m in range(1, months + 1):
            at = now - timedelta(days=30 * m)
            feats = compute_features(h, at)
            horizon = at + timedelta(days=30)
            label = any(
                at < v.occurred_at <= horizon and v.severity in ("high", "critical") for v in h.violations
            )
            xs.append([feats[k] for k in FEATURES])
            ys.append(int(label))
    return np.array(xs, dtype=float), np.array(ys, dtype=int)


def train(x: np.ndarray, y: np.ndarray) -> TrainedModel | None:
    """Train when there is enough labelled data with both classes; else ``None``."""
    if len(y) < MIN_TRAINING_SAMPLES or len(set(y.tolist())) < 2 or min(np.bincount(y)) < 5:
        return None
    pipeline = Pipeline(
        [
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(class_weight="balanced", C=0.5, max_iter=2000)),
        ]
    )
    folds = min(5, int(min(np.bincount(y))))
    cv_prob = cross_val_predict(
        pipeline, x, y, cv=StratifiedKFold(n_splits=folds, shuffle=True, random_state=42), method="predict_proba"
    )[:, 1]
    auc = float(roc_auc_score(y, cv_prob))
    pipeline.fit(x, y)
    version = datetime.now(UTC).strftime("logreg-%Y%m%d%H%M%S")
    return TrainedModel(
        pipeline,
        version,
        {"cv_roc_auc": round(auc, 4), "positive_rate": round(float(y.mean()), 4)},
        int(len(y)),
    )


def contractor_compliance_score(features: dict[str, float]) -> float:
    """0-100 contractor compliance score (100 = clean record), shown in the registry."""
    penalty = (
        features["critical_90d"] * 18
        + features["high_90d"] * 8
        + features["medium_90d"] * 3
        + features["low_90d"] * 1
        + features["overdue_actions"] * 6
        + features["open_violations"] * 1.5
    )
    return round(max(0.0, 100.0 - penalty), 1)
