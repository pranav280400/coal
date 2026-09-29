"""Document repository with OCR digitisation pipeline (FR14)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import UploadFile
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.models import Document, Mine
from app.models.enums import DocumentType, ProcessingStatus, Role
from app.services import media
from app.services.access import Perm, Principal, assert_mine_access, visible_mine_ids
from app.services.events import record_event


def digitize_workflow_id(document_id: uuid.UUID | str) -> str:
    return f"document-digitize-{document_id}"


async def _scope(stmt: Select[Any], session: AsyncSession, principal: Principal) -> Select[Any]:
    if principal.is_global:
        return stmt
    mines = await visible_mine_ids(session, principal) or []
    conditions = [Document.mine_id.in_(mines)] if mines else []
    if principal.subsidiary_id and principal.role == Role.CORPORATE:
        conditions.append(Document.subsidiary_id == principal.subsidiary_id)
    # Organisation-wide circulars/regulations (no mine, no subsidiary) are visible to everyone.
    conditions.append(Document.mine_id.is_(None) & Document.subsidiary_id.is_(None))
    return stmt.where(or_(*conditions))


async def list_documents(
    session: AsyncSession,
    principal: Principal,
    *,
    mine_id: uuid.UUID | None,
    doc_type: DocumentType | None,
    status: ProcessingStatus | None,
    q: str | None,
    offset: int,
    limit: int,
) -> tuple[list[Document], int]:
    stmt = await _scope(select(Document), session, principal)
    if mine_id:
        stmt = stmt.where(Document.mine_id == mine_id)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if status:
        stmt = stmt.where(Document.ocr_status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Document.title.ilike(like), Document.filename.ilike(like), Document.ocr_text.ilike(like)))
    total = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (
        await session.execute(stmt.order_by(Document.created_at.desc()).offset(offset).limit(limit))
    ).scalars().all()
    return list(rows), int(total)


async def get_document(session: AsyncSession, principal: Principal, document_id: uuid.UUID) -> Document:
    stmt = await _scope(select(Document).where(Document.id == document_id), session, principal)
    doc = (await session.execute(stmt)).scalars().first()
    if doc is None:
        raise NotFound("Document not found")
    return doc


async def upload_document(
    session: AsyncSession,
    principal: Principal,
    *,
    upload: UploadFile,
    title: str,
    doc_type: DocumentType,
    mine_id: uuid.UUID | None,
    language: str,
) -> Document:
    principal.require(Perm.DOCUMENT_WRITE)
    subsidiary_id = principal.subsidiary_id
    if mine_id:
        mine: Mine = await assert_mine_access(session, principal, mine_id, write=True)
        subsidiary_id = mine.subsidiary_id
    elif principal.role == Role.MINE_OFFICIAL:
        mine_id = principal.mine_id
    data, ctype, ext, filename = await media.read_upload(upload, media.DOCUMENT_TYPES)
    stored = await media.store_bytes("documents", data, ctype, ext, filename)
    doc = Document(
        mine_id=mine_id,
        subsidiary_id=subsidiary_id,
        title=title,
        doc_type=doc_type,
        storage_key=stored.key,
        filename=stored.filename,
        content_type=stored.content_type,
        size_bytes=stored.size,
        sha256=stored.sha256,
        language=language,
        uploaded_by=principal.id,
    )
    session.add(doc)
    await session.flush()
    doc.workflow_id = digitize_workflow_id(doc.id)
    record_event(
        session, "document.uploaded", entity_type="document", entity_id=doc.id, actor=principal,
        mine_id=mine_id, subsidiary_id=subsidiary_id,
        after={"title": title, "doc_type": doc_type.value, "sha256": stored.sha256, "size": stored.size},
    )
    await session.commit()
    return doc
