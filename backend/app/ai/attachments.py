"""Files attached to an assistant conversation.

The text is extracted once on upload (PDF text layer, or OCR for scans and photos)
and kept in Redis for a day, scoped to the uploading user. When a question is asked,
only the passages most relevant to it are put in front of the model — the CPU-hosted
model reads roughly 15 tokens a second, so a whole document would take minutes.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from app.core.redis import cache_get_json, cache_set_json

TTL_SECONDS = 24 * 3600
MAX_TEXT_CHARS = 60_000
EXCERPT_BUDGET = 1_200  # characters of attachment text sent with each question

_STOP = set("""a an and are as at be by can do does for from has have how i if in is it its me my of on or our should
that the their them there these this to was what when where which who why will with you your please about tell give
file document attached pdf image upload uploaded""".split())  # noqa: SIM905 - readable word list
_SUMMARY = re.compile(r"\b(summar|overview|what is (this|the) (file|document)|explain (this|the)|key points|main points|सार)", re.I)


def _key(user_id: str, att_id: str) -> str:
    return f"cmg:ai:att:{user_id}:{att_id}"


def clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


async def save(user_id: str, *, filename: str, content_type: str, pages: int, text: str, method: str) -> dict[str, Any]:
    att_id = uuid.uuid4().hex
    body = clean(text)
    record = {"id": att_id, "filename": filename, "content_type": content_type, "pages": pages,
              "chars": len(body), "method": method, "text": body}
    await cache_set_json(_key(user_id, att_id), record, TTL_SECONDS)
    return {k: v for k, v in record.items() if k != "text"} | {"preview": body[:240]}


async def load(user_id: str, ids: list[str]) -> list[dict[str, Any]]:
    out = []
    for att_id in ids[:3]:
        if not re.fullmatch(r"[0-9a-f]{32}", att_id):
            continue
        rec = await cache_get_json(_key(user_id, att_id))
        if rec:
            out.append(rec)
    return out


def _chunks(text: str, size: int = 420) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n|(?=--- Page \d+ ---)", text) if p.strip()]
    chunks: list[str] = []
    for p in paras:
        while len(p) > size:
            cut = p.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 2 else size
            chunks.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            chunks.append(p)
    return chunks


def excerpt(question: str, text: str, budget: int = EXCERPT_BUDGET) -> str:
    """The passages of an attachment that best match the question (or its opening, for a summary)."""
    chunks = _chunks(text)
    if not chunks:
        return ""
    if _SUMMARY.search(question):
        picked = list(range(len(chunks)))
    else:
        words = {w for w in re.findall(r"[a-z0-9ऀ-ॿ]{3,}", question.lower()) if w not in _STOP}
        scored = []
        for i, c in enumerate(chunks):
            low = c.lower()
            score = sum(low.count(w) for w in words)
            scored.append((score, -i, i))
        scored.sort(reverse=True)
        picked = sorted(i for s, _, i in scored if s > 0) or list(range(len(chunks)))
    out, used = [], 0
    for i in picked:
        c = chunks[i]
        if used + len(c) > budget:
            if not out:
                out.append(c[:budget])
            break
        out.append(c)
        used += len(c) + 2
    return "\n\n".join(out)
