"""Field-level PII encryption and hashing helpers."""

from __future__ import annotations

import hashlib
import hmac
import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings


@lru_cache
def _fernet() -> MultiFernet:
    # PII_ENCRYPTION_KEY may hold several comma-separated keys: the first encrypts,
    # all decrypt. This enables zero-downtime key rotation.
    keys = [k.strip() for k in get_settings().pii_encryption_key.get_secret_value().split(",")]
    return MultiFernet([Fernet(k.encode()) for k in keys if k])


def encrypt_str(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_str(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:  # pragma: no cover - indicates key misconfiguration
        raise ValueError("Unable to decrypt PII field; check PII_ENCRYPTION_KEY") from exc


class EncryptedString(TypeDecorator[str]):
    """Transparently encrypts a string column at rest with Fernet (AES-128-CBC + HMAC)."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        return encrypt_str(value) if value else None

    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        return decrypt_str(value) if value else None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(payload: Any) -> str:
    """Deterministic JSON used for hash-chaining audit entries."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def chain_hash(prev_hash: str, payload: Any) -> str:
    return hashlib.sha256((prev_hash + canonical_json(payload)).encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
