"""Qdrant knowledge base: regulations, inspections, violations and OCR'd documents.

A single collection holds all sources with payload fields used for tenant
filtering (``mine_id``/``subsidiary_id``) so RAG answers never leak data across
mines a user may not see. Regulations carry no mine and are visible to all.
"""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.ai import llm
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_NAMESPACE = uuid.UUID("5b0c7f7e-3f55-4d8e-9a2b-0c0a1d1e2f33")


@lru_cache
def qdrant() -> AsyncQdrantClient:
    s = get_settings()
    return AsyncQdrantClient(
        url=s.qdrant_url,
        api_key=s.qdrant_api_key.get_secret_value() if s.qdrant_api_key else None,
        timeout=30,
    )


async def ensure_collection() -> None:
    s = get_settings()
    client = qdrant()
    if not await client.collection_exists(s.qdrant_collection):
        await client.create_collection(
            collection_name=s.qdrant_collection,
            vectors_config=models.VectorParams(size=s.embedding_dim, distance=models.Distance.COSINE),
            optimizers_config=models.OptimizersConfigDiff(default_segment_number=2),
        )
        logger.info("created qdrant collection %s", s.qdrant_collection)
    for field, schema in (
        ("source_type", models.PayloadSchemaType.KEYWORD),
        ("source_id", models.PayloadSchemaType.KEYWORD),
        ("mine_id", models.PayloadSchemaType.KEYWORD),
        ("subsidiary_id", models.PayloadSchemaType.KEYWORD),
        ("category", models.PayloadSchemaType.KEYWORD),
        ("public", models.PayloadSchemaType.BOOL),
    ):
        try:
            await client.create_payload_index(s.qdrant_collection, field_name=field, field_schema=schema)
        except Exception:  # index already exists
            pass


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Paragraph-aware chunking with overlap."""
    text = text.strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in text.replace("\r", "").split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        while len(para) > max_chars:
            head, para = para[:max_chars], para[max_chars - overlap :]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            tail = current[-overlap:] if current else ""
            current = f"{tail}\n\n{para}" if tail else para
    if current:
        chunks.append(current)
    return chunks


def point_id(source_type: str, source_id: str, chunk: int) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{source_type}:{source_id}:{chunk}"))


async def upsert_source(
    *,
    source_type: str,
    source_id: str,
    title: str,
    text: str,
    mine_id: str | None = None,
    subsidiary_id: str | None = None,
    category: str | None = None,
    extra: dict[str, Any] | None = None,
) -> int:
    """(Re)index one source document; returns number of chunks stored."""
    s = get_settings()
    chunks = chunk_text(text)
    await delete_source(source_type, source_id)
    if not chunks:
        return 0
    stored = 0
    for start in range(0, len(chunks), 32):
        batch = chunks[start : start + 32]
        vectors = await llm.embed([f"{title}\n{c}" for c in batch])
        points = [
            models.PointStruct(
                id=point_id(source_type, source_id, start + i),
                vector=vec,
                payload={
                    "source_type": source_type,
                    "source_id": source_id,
                    "title": title,
                    "text": chunk,
                    "chunk": start + i,
                    "mine_id": mine_id,
                    "subsidiary_id": subsidiary_id,
                    "category": category,
                    "public": mine_id is None and subsidiary_id is None,
                    **(extra or {}),
                },
            )
            for i, (chunk, vec) in enumerate(zip(batch, vectors, strict=True))
        ]
        await qdrant().upsert(s.qdrant_collection, points=points, wait=True)
        stored += len(points)
    return stored


async def delete_source(source_type: str, source_id: str) -> None:
    s = get_settings()
    await qdrant().delete(
        s.qdrant_collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(key="source_type", match=models.MatchValue(value=source_type)),
                    models.FieldCondition(key="source_id", match=models.MatchValue(value=source_id)),
                ]
            )
        ),
    )


def tenant_filter(
    visible_mine_ids: list[str] | None,
    source_types: list[str] | None = None,
    exclude_source_id: str | None = None,
) -> models.Filter:
    must: list[Any] = []
    must_not: list[Any] = []
    if source_types:
        must.append(models.FieldCondition(key="source_type", match=models.MatchAny(any=source_types)))
    if visible_mine_ids is not None:
        should: list[Any] = [models.FieldCondition(key="public", match=models.MatchValue(value=True))]
        if visible_mine_ids:
            should.append(models.FieldCondition(key="mine_id", match=models.MatchAny(any=visible_mine_ids)))
        must.append(models.Filter(should=should))
    if exclude_source_id:
        must_not.append(models.FieldCondition(key="source_id", match=models.MatchValue(value=exclude_source_id)))
    return models.Filter(must=must or None, must_not=must_not or None)


async def search(
    query: str,
    *,
    visible_mine_ids: list[str] | None,
    source_types: list[str] | None = None,
    limit: int = 8,
    exclude_source_id: str | None = None,
    score_threshold: float | None = 0.3,
) -> list[dict[str, Any]]:
    s = get_settings()
    [vector] = await llm.embed([query])
    result = await qdrant().query_points(
        s.qdrant_collection,
        query=vector,
        query_filter=tenant_filter(visible_mine_ids, source_types, exclude_source_id),
        limit=limit,
        with_payload=True,
        score_threshold=score_threshold,
    )
    hits = []
    for point in result.points:
        payload = point.payload or {}
        hits.append(
            {
                "source_type": payload.get("source_type"),
                "source_id": payload.get("source_id"),
                "title": payload.get("title"),
                "text": payload.get("text", ""),
                "mine_id": payload.get("mine_id"),
                "score": float(point.score),
            }
        )
    return hits


async def health() -> bool:
    try:
        await qdrant().get_collections()
        return True
    except Exception:
        return False
