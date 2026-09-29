"""S3-compatible object storage (AWS S3, MinIO, Ceph RGW, NIC cloud object storage)."""

from __future__ import annotations

import io
from functools import lru_cache
from typing import Any

import anyio
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


def _is_aws() -> bool:
    return not get_settings().s3_endpoint_url


def _client(endpoint: str | None) -> Any:
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )


@lru_cache
def _internal() -> Any:
    return _client(get_settings().s3_endpoint_url)


@lru_cache
def _public() -> Any:
    """Client used only to sign URLs with the hostname browsers can reach."""
    settings = get_settings()
    return _client(settings.s3_public_endpoint_url or settings.s3_endpoint_url)


async def ensure_bucket() -> None:
    settings = get_settings()

    def _ensure() -> None:
        client = _internal()
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
        except ClientError:
            # AWS (and strict S3-compatible stores) require a LocationConstraint outside
            # us-east-1; MinIO-style stores may reject it, so retry without on failure.
            if settings.s3_region != "us-east-1":
                try:
                    client.create_bucket(
                        Bucket=settings.s3_bucket,
                        CreateBucketConfiguration={"LocationConstraint": settings.s3_region},
                    )
                except ClientError:
                    if _is_aws():
                        raise
                    client.create_bucket(Bucket=settings.s3_bucket)
            else:
                client.create_bucket(Bucket=settings.s3_bucket)
        if _is_aws():
            client.put_public_access_block(
                Bucket=settings.s3_bucket,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )

    await anyio.to_thread.run_sync(_ensure)


async def put_object(key: str, data: bytes, content_type: str, metadata: dict[str, str] | None = None) -> None:
    settings = get_settings()
    kwargs: dict[str, Any] = {
        "Bucket": settings.s3_bucket,
        "Key": key,
        "Body": data,
        "ContentType": content_type,
        "Metadata": metadata or {},
    }
    if _is_aws():
        kwargs["ServerSideEncryption"] = "AES256"
    await anyio.to_thread.run_sync(lambda: _internal().put_object(**kwargs))


async def get_object(key: str) -> bytes:
    settings = get_settings()

    def _get() -> bytes:
        buf = io.BytesIO()
        _internal().download_fileobj(settings.s3_bucket, key, buf)
        return buf.getvalue()

    return await anyio.to_thread.run_sync(_get)


async def delete_object(key: str) -> None:
    settings = get_settings()
    await anyio.to_thread.run_sync(lambda: _internal().delete_object(Bucket=settings.s3_bucket, Key=key))


async def presigned_get_url(key: str, filename: str | None = None, inline: bool = False) -> str:
    settings = get_settings()
    params: dict[str, Any] = {"Bucket": settings.s3_bucket, "Key": key}
    if filename:
        safe = filename.replace('"', "").replace("\n", " ")
        disposition = "inline" if inline else "attachment"
        params["ResponseContentDisposition"] = f'{disposition}; filename="{safe}"'
    return await anyio.to_thread.run_sync(
        lambda: _public().generate_presigned_url(
            "get_object", Params=params, ExpiresIn=settings.s3_presign_ttl_seconds
        )
    )


async def ping() -> bool:
    settings = get_settings()
    try:
        await anyio.to_thread.run_sync(lambda: _internal().head_bucket(Bucket=settings.s3_bucket))
        return True
    except Exception:
        return False
