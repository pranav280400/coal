"""Validated file uploads to object storage (evidence photos, documents)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import MediaFile

# Magic-byte sniffing: the declared Content-Type is never trusted on its own.
_SIGNATURES: list[tuple[bytes, int, str, str]] = [
    (b"\xff\xd8\xff", 0, "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", 0, "image/png", "png"),
    (b"RIFF", 0, "image/webp", "webp"),  # confirmed below by WEBP marker
    (b"II*\x00", 0, "image/tiff", "tif"),
    (b"MM\x00*", 0, "image/tiff", "tif"),
    (b"%PDF-", 0, "application/pdf", "pdf"),
]

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff"}
DOCUMENT_TYPES = IMAGE_TYPES | {"application/pdf", "text/plain"}


class UploadRejected(AppError):
    status_code = 415
    code = "unsupported_media"


@dataclass(slots=True)
class StoredFile:
    key: str
    filename: str
    content_type: str
    size: int
    sha256: str


def sniff(data: bytes, declared: str | None) -> tuple[str, str]:
    for sig, offset, ctype, ext in _SIGNATURES:
        if data[offset : offset + len(sig)] == sig:
            if ctype == "image/webp" and data[8:12] != b"WEBP":
                continue
            return ctype, ext
    if declared in ("text/plain", "text/csv", "text/markdown"):
        try:
            data[:4096].decode("utf-8")
            return "text/plain", "txt"
        except UnicodeDecodeError:
            pass
    raise UploadRejected("File type not recognised or not allowed")


def _safe_name(name: str | None, ext: str) -> str:
    base = (name or f"upload.{ext}").replace("\\", "/").split("/")[-1]
    cleaned = "".join(c for c in base if c.isalnum() or c in "._- ")[:200].strip() or f"upload.{ext}"
    return cleaned


async def read_upload(upload: UploadFile, allowed: set[str]) -> tuple[bytes, str, str, str]:
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise UploadRejected(f"File exceeds {get_settings().max_upload_mb} MB limit")
    if not data:
        raise UploadRejected("Empty file")
    ctype, ext = sniff(data, upload.content_type)
    if ctype not in allowed:
        raise UploadRejected(f"{ctype} is not allowed here")
    return data, ctype, ext, _safe_name(upload.filename, ext)


async def store_bytes(prefix: str, data: bytes, ctype: str, ext: str, filename: str) -> StoredFile:
    digest = hashlib.sha256(data).hexdigest()
    key = f"{prefix}/{datetime.now(UTC):%Y/%m}/{uuid.uuid4().hex}.{ext}"
    await storage.put_object(key, data, ctype, {"sha256": digest})
    return StoredFile(key, filename, ctype, len(data), digest)


async def attach_media(
    session: AsyncSession,
    *,
    entity_type: str,
    entity_id: uuid.UUID,
    upload: UploadFile,
    uploaded_by: uuid.UUID,
    latitude: float | None,
    longitude: float | None,
    captured_at: datetime | None,
) -> MediaFile:
    data, ctype, ext, filename = await read_upload(upload, IMAGE_TYPES | {"application/pdf"})
    stored = await store_bytes(f"media/{entity_type}/{entity_id}", data, ctype, ext, filename)
    media = MediaFile(
        entity_type=entity_type,
        entity_id=entity_id,
        storage_key=stored.key,
        filename=stored.filename,
        content_type=stored.content_type,
        size_bytes=stored.size,
        sha256=stored.sha256,
        latitude=latitude,
        longitude=longitude,
        captured_at=captured_at,
        uploaded_by=uploaded_by,
    )
    session.add(media)
    await session.flush()
    return media


async def list_media(session: AsyncSession, entity_type: str, entity_id: uuid.UUID) -> list[MediaFile]:
    return list(
        (
            await session.execute(
                select(MediaFile)
                .where(MediaFile.entity_type == entity_type, MediaFile.entity_id == entity_id)
                .order_by(MediaFile.created_at)
            )
        ).scalars().all()
    )
