"""AI-assisted violation severity classification (FR5: AI-assisted, human-confirmed).

The LLM (via LiteLLM -> vLLM) proposes a severity with rationale, grounded on the
most similar regulations/past violations from Qdrant. If the AI service is down,
a deterministic rules engine derived from DGMS hazard categories produces the
suggestion instead, clearly marked ``source="rules"``. Either way a human must
confirm the severity before it is treated as final.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.ai import llm, vectorstore
from app.models.enums import Severity

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SeveritySuggestion:
    severity: Severity
    confidence: float
    rationale: str
    source: str  # "llm" | "rules"
    regulation_refs: list[str]


# Weighted hazard lexicon (English + common Hindi/Hinglish field terms).
_RULES: list[tuple[Severity, float, tuple[str, ...]]] = [
    (Severity.CRITICAL, 5.0, (
        "fatal", "fatality", "death", "died", "explosion", "firedamp", "methane above", "roof fall",
        "side fall", "inrush", "inundation", "entrapped", "trapped", "collapse", "gas outburst",
        "spontaneous heating", "mine fire", "mrityu", "maut", "visphot",
    )),
    (Severity.HIGH, 3.0, (
        "serious injury", "injured", "injury", "methane", "ch4", "gas", "no ventilation", "ventilation failure",
        "unsupported roof", "support missing", "dumper", "brake failure", "overloaded", "blasting",
        "misfire", "explosive", "unauthorised entry", "electrical shock", "high voltage", "fire",
        "dust explosion", "no permit", "without permit", "slope failure", "bench collapse", "crack",
        "chot", "aag",
    )),
    (Severity.MEDIUM, 1.5, (
        "ppe", "helmet", "safety shoes", "self rescuer", "dust", "noise", "effluent", "water quality",
        "air quality", "pm10", "pm2.5", "spill", "overdue", "expired", "calibration", "first aid",
        "fencing", "signage", "illumination", "lighting", "training", "vocational", "medical examination",
    )),
    (Severity.LOW, 0.8, (
        "housekeeping", "record", "register", "documentation", "display", "notice board", "minor",
        "cleanliness", "labelling", "form", "late submission",
    )),
]

_REG_PATTERN = re.compile(r"\b(?:reg(?:ulation)?\.?|section|sec\.?|rule)\s*\d+[a-z]?(?:\(\d+\))?", re.I)


# Whole-word/phrase matching so e.g. "ppe" does not fire inside "stopped".
_TERM_PATTERNS: dict[str, re.Pattern[str]] = {
    term: re.compile(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])")
    for _, _, terms in _RULES
    for term in terms
}


def classify_rules(title: str, description: str) -> SeveritySuggestion:
    text = f"{title} {description}".lower()
    scores: dict[Severity, float] = {s: 0.0 for s in Severity}
    matched: list[str] = []
    for severity, weight, terms in _RULES:
        for term in terms:
            if _TERM_PATTERNS[term].search(text):
                scores[severity] += weight
                matched.append(term)
    if not matched:
        return SeveritySuggestion(
            Severity.MEDIUM, 0.35, "No hazard keywords matched; defaulted to medium for human review.",
            "rules", _REG_PATTERN.findall(description),
        )
    # Highest severity with any evidence wins; confidence grows with evidence mass.
    order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
    chosen = next(s for s in order if scores[s] > 0)
    total = sum(scores.values())
    confidence = min(0.85, 0.4 + 0.45 * (scores[chosen] / total) * min(1.0, total / 6))
    return SeveritySuggestion(
        chosen,
        round(confidence, 2),
        f"Rule-based assessment: matched hazard indicators {sorted(set(matched))[:8]}.",
        "rules",
        _REG_PATTERN.findall(description),
    )


_SYSTEM = (
    "You are a senior DGMS (Directorate General of Mines Safety) inspector assessing coal-mine "
    "compliance violations in India. Classify severity strictly as one of: low, medium, high, critical.\n"
    "critical = imminent danger to life or already caused fatality/major accident (roof fall, fire, "
    "explosion, inundation, gas above limits);\n"
    "high = serious hazard likely to cause injury or major environmental harm if not fixed quickly;\n"
    "medium = statutory non-compliance with moderate risk (PPE, dust, effluent limits, expired certificates);\n"
    "low = administrative/documentation lapses with negligible direct risk.\n"
    "Respond ONLY with JSON: {\"severity\": str, \"confidence\": number 0-1, \"rationale\": str (<=60 words), "
    "\"regulation_refs\": [str]}. The description may be in English, Hindi or other Indian languages."
)


async def classify(
    title: str, description: str, category: str, *, visible_mine_ids: list[str] | None = None
) -> SeveritySuggestion:
    try:
        context = ""
        try:
            hits = await vectorstore.search(
                f"{title}. {description}",
                visible_mine_ids=visible_mine_ids,
                source_types=["regulation", "violation"],
                limit=4,
            )
            context = "\n".join(f"- [{h['source_type']}] {h['title']}: {h['text'][:400]}" for h in hits)
        except Exception as exc:  # vector search is an enhancement, not a requirement
            logger.info("classifier context unavailable: %s", exc)
        user = (
            f"Category: {category}\nTitle: {title}\nDescription: {description}\n\n"
            f"Relevant regulations and similar past cases:\n{context or '(none available)'}"
        )
        data = await llm.chat_json(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            operation="classify_severity",
        )
        severity = Severity(str(data.get("severity", "")).lower().strip())
        confidence = float(data.get("confidence", 0.6))
        return SeveritySuggestion(
            severity,
            max(0.0, min(1.0, confidence)),
            str(data.get("rationale", ""))[:1000],
            "llm",
            [str(r) for r in data.get("regulation_refs", [])][:10],
        )
    except Exception as exc:
        logger.warning("LLM severity classification failed, using rules engine: %s", exc)
        return classify_rules(title, description)
