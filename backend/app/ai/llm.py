"""LLM access through the LiteLLM gateway (OpenAI-compatible), backed by vLLM.

All model calls go through LiteLLM so models can be swapped/routed centrally
(e.g. ``cmg-chat`` -> vLLM Llama/Qwen, ``cmg-embed`` -> vLLM bge-m3) without
touching application code.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI, BadRequestError

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable
from app.core.metrics import LLM_LATENCY, LLM_REQUESTS

logger = logging.getLogger(__name__)


class LLMUnavailable(ServiceUnavailable):
    code = "ai_unavailable"


class LLMBadRequest(ValueError):
    """The gateway rejected the request parameters (e.g. unsupported response_format)."""


@lru_cache
def client() -> AsyncOpenAI:
    s = get_settings()
    return AsyncOpenAI(
        base_url=s.llm_base_url,
        api_key=s.llm_api_key.get_secret_value(),
        timeout=s.llm_timeout_seconds,
        max_retries=2,
    )


async def chat(
    messages: list[dict[str, str]],
    *,
    operation: str = "chat",
    max_tokens: int | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
) -> str:
    s = get_settings()
    start = time.perf_counter()
    kwargs: dict[str, Any] = {
        "model": s.llm_chat_model,
        "messages": messages,
        "max_tokens": max_tokens or s.llm_max_tokens,
        "temperature": s.llm_temperature if temperature is None else temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = await client().chat.completions.create(**kwargs)
    except BadRequestError as exc:
        LLM_REQUESTS.labels(operation, "bad_request").inc()
        raise LLMBadRequest(str(exc)) from exc
    except (APIConnectionError, APITimeoutError, APIError) as exc:
        LLM_REQUESTS.labels(operation, "error").inc()
        logger.warning("llm call failed", extra={"operation": operation, "error": str(exc)})
        raise LLMUnavailable("The AI service is currently unavailable") from exc
    finally:
        LLM_LATENCY.labels(operation).observe(time.perf_counter() - start)
    LLM_REQUESTS.labels(operation, "ok").inc()
    return (resp.choices[0].message.content or "").strip()


async def chat_stream(
    messages: list[dict[str, str]], *, operation: str = "chat_stream", max_tokens: int | None = None
) -> AsyncIterator[str]:
    s = get_settings()
    start = time.perf_counter()
    try:
        stream = await client().chat.completions.create(
            model=s.llm_chat_model,
            messages=messages,
            max_tokens=max_tokens or s.llm_max_tokens,
            temperature=s.llm_temperature,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
        LLM_REQUESTS.labels(operation, "ok").inc()
    except (APIConnectionError, APITimeoutError, APIError) as exc:
        LLM_REQUESTS.labels(operation, "error").inc()
        raise LLMUnavailable("The AI service is currently unavailable") from exc
    finally:
        LLM_LATENCY.labels(operation).observe(time.perf_counter() - start)


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


async def chat_json(messages: list[dict[str, str]], *, operation: str, max_tokens: int = 600) -> dict[str, Any]:
    """Ask for a JSON object; tolerant of models that wrap JSON in prose/fences."""
    try:
        raw = await chat(messages, operation=operation, max_tokens=max_tokens, temperature=0.0, json_mode=True)
    except LLMBadRequest:  # some backends reject response_format; retry without it
        raw = await chat(messages, operation=operation, max_tokens=max_tokens, temperature=0.0)
    match = _JSON_BLOCK.search(raw)
    if not match:
        raise ValueError("model did not return JSON")
    return json.loads(match.group(0))


async def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if not texts:
        return []
    start = time.perf_counter()
    try:
        resp = await client().embeddings.create(model=s.llm_embedding_model, input=texts)
    except (APIConnectionError, APITimeoutError, APIError) as exc:
        LLM_REQUESTS.labels("embed", "error").inc()
        raise LLMUnavailable("The embedding service is currently unavailable") from exc
    finally:
        LLM_LATENCY.labels("embed").observe(time.perf_counter() - start)
    LLM_REQUESTS.labels("embed", "ok").inc()
    vectors = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
    if vectors and len(vectors[0]) != s.embedding_dim:
        raise ValueError(
            f"Embedding dimension mismatch: model returned {len(vectors[0])}, EMBEDDING_DIM={s.embedding_dim}"
        )
    return vectors


async def warm_up(messages: list[dict[str, str]] | None = None) -> None:
    """Load the chat and embedding models into memory so the first question is not a cold start."""
    try:
        await embed(["warm-up"])
        await chat(messages or [{"role": "user", "content": "Reply with OK."}], operation="warm_up", max_tokens=1)
        logger.info("AI models warmed up")
    except Exception as exc:  # noqa: BLE001 - the app works without AI
        logger.warning("AI warm-up skipped: %s", exc)


async def health() -> bool:
    try:
        await client().models.list()
        return True
    except Exception:
        return False
