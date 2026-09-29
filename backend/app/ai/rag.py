"""Retrieval-augmented compliance assistant (FR9, FR10) — multilingual, tenant-scoped."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.ai import llm, vectorstore

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "or": "Odia",
    "te": "Telugu",
    "mr": "Marathi",
    "ta": "Tamil",
}

SYSTEM_PROMPT = """You are Lumen Assistant, an expert on Indian coal-mine governance: the Mines Act 1952, \
Coal Mines Regulations 2017, Mines Rules 1955, Environment (Protection) Act 1986, Water/Air Acts, \
the Contract Labour Act 1970, the new Labour Codes, and DGMS circulars. You help mine officials, \
corporate managers and regulators with compliance questions, inspection findings and risk.

Rules:
- Ground every factual claim in the CONTEXT below and cite sources inline as [1], [2]… matching the context numbers.
- If the context does not contain the answer, say so plainly and suggest who to consult; never invent regulation numbers.
- Use the LIVE DATA snapshot for questions about current counts/status of the user's mines.
- Be concise and practical: numbered steps for procedures, short tables for comparisons.
- {language_rule}
"""


def build_messages(
    question: str,
    hits: list[dict[str, Any]],
    history: list[dict[str, str]],
    live_data: str,
    language: str | None,
) -> list[dict[str, str]]:
    if language and language not in ("auto", "") and language in LANGUAGE_NAMES:
        language_rule = f"Always answer in {LANGUAGE_NAMES[language]}, keeping statutory references verbatim."
    else:
        language_rule = "Answer in the same language the user wrote in (English, Hindi or another Indian language)."
    context = "\n\n".join(
        f"[{i + 1}] ({h['source_type']}) {h['title']}\n{h['text'][:1500]}" for i, h in enumerate(hits)
    ) or "(no matching documents found)"
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(language_rule=language_rule)},
        {"role": "system", "content": f"LIVE DATA (user's scope):\n{live_data}\n\nCONTEXT:\n{context}"},
    ]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": question})
    return messages


def citations(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "index": i + 1,
            "source_type": h["source_type"],
            "source_id": h["source_id"],
            "title": h["title"],
            "score": round(h["score"], 3),
            "snippet": h["text"][:240],
        }
        for i, h in enumerate(hits)
    ]


async def retrieve(question: str, visible_mine_ids: list[str] | None, top_k: int) -> list[dict[str, Any]]:
    try:
        return await vectorstore.search(question, visible_mine_ids=visible_mine_ids, limit=top_k, score_threshold=0.25)
    except llm.LLMUnavailable:
        raise
    except Exception as exc:
        logger.warning("retrieval failed: %s", exc)
        return []


async def answer_stream(
    question: str,
    *,
    hits: list[dict[str, Any]],
    history: list[dict[str, str]],
    live_data: str,
    language: str | None,
) -> AsyncIterator[str]:
    messages = build_messages(question, hits, history, live_data, language)
    async for token in llm.chat_stream(messages, operation="assistant"):
        yield token


async def summarize_inspection(inspection: dict[str, Any], language: str = "en") -> dict[str, Any]:
    """Structured summary + findings of an inspection report (FR10)."""
    lang = LANGUAGE_NAMES.get(language, "English")
    prompt = (
        "Summarise this coal-mine inspection for senior management in "
        f"{lang}. Return JSON with keys: summary (<=120 words), key_findings (list of strings), "
        "hazards (list of {description, severity: low|medium|high|critical, category: "
        "safety|environment|production|labour}), recommended_actions (list of strings), "
        "overall_outcome (compliant|minor_issues|non_compliant).\n\n"
        f"INSPECTION:\n{inspection}"
    )
    return await llm.chat_json(
        [
            {"role": "system", "content": "You are a meticulous DGMS mine-safety analyst. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        operation="summarize_inspection",
        max_tokens=900,
    )


async def structure_document(text: str, filename: str) -> dict[str, Any]:
    """Clean OCR text and extract structured governance fields from a legacy record."""
    excerpt = text[:12000]
    prompt = (
        "The following text was OCR'd from a scanned coal-mine governance record (may mix English and Hindi, "
        "contain OCR noise). Return JSON with keys: document_type (statutory_return|inspection_report|permit|"
        "license|circular|regulation|evidence|other), title, issue_date (YYYY-MM-DD or null), "
        "expiry_date (YYYY-MM-DD or null), issuing_authority, mine_name, regulation_refs (list), "
        "key_obligations (list of strings), summary (<=100 words, English).\n\n"
        f"FILENAME: {filename}\nTEXT:\n{excerpt}"
    )
    return await llm.chat_json(
        [
            {"role": "system", "content": "You extract structured data from noisy OCR text. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        operation="structure_document",
        max_tokens=900,
    )


async def report_narrative(metrics: dict[str, Any], scope_label: str, period: str) -> str:
    prompt = (
        f"Write the executive summary (180-250 words) of the statutory compliance report for {scope_label}, "
        f"period {period}, for the Ministry of Coal / DGMS. Cover overall compliance, critical violations, "
        "overdue items, high-risk sites, trends, and 3 priority recommendations. Use only these metrics:\n"
        f"{metrics}"
    )
    return await llm.chat(
        [
            {"role": "system", "content": "You write precise, formal government compliance reports."},
            {"role": "user", "content": prompt},
        ],
        operation="report_summary",
        max_tokens=700,
    )
