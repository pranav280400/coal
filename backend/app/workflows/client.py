"""Temporal client shared by the API and Kafka consumers."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from temporalio.client import Client, TLSConfig, WorkflowHandle
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError

from app.core.config import get_settings
from app.core.errors import ServiceUnavailable
from app.core.metrics import WORKFLOWS_STARTED

logger = logging.getLogger(__name__)

_client: Client | None = None
_lock = asyncio.Lock()


async def get_client() -> Client:
    global _client
    async with _lock:
        if _client is None:
            s = get_settings()
            tls: TLSConfig | bool = False
            if s.temporal_tls_cert_path and s.temporal_tls_key_path:
                with open(s.temporal_tls_cert_path, "rb") as c, open(s.temporal_tls_key_path, "rb") as k:
                    tls = TLSConfig(client_cert=c.read(), client_private_key=k.read())
            elif s.temporal_api_key:
                tls = True
            _client = await Client.connect(
                s.temporal_host,
                namespace=s.temporal_namespace,
                tls=tls,
                api_key=s.temporal_api_key.get_secret_value() if s.temporal_api_key else None,
            )
    return _client


async def start_workflow(workflow: str, arg: Any, *, workflow_id: str, **kwargs: Any) -> WorkflowHandle | None:
    """Idempotently start a workflow; returns None if one with this id is already running."""
    try:
        client = await get_client()
    except Exception as exc:
        raise ServiceUnavailable("Workflow engine is unavailable") from exc
    try:
        handle = await client.start_workflow(
            workflow,
            arg,
            id=workflow_id,
            task_queue=get_settings().temporal_task_queue,
            id_reuse_policy=kwargs.pop("id_reuse_policy", WorkflowIDReusePolicy.ALLOW_DUPLICATE_FAILED_ONLY),
            id_conflict_policy=kwargs.pop("id_conflict_policy", WorkflowIDConflictPolicy.FAIL),
            **kwargs,
        )
        WORKFLOWS_STARTED.labels(workflow).inc()
        return handle
    except WorkflowAlreadyStartedError:
        return None


async def signal(workflow_id: str, signal_name: str, arg: Any = None) -> bool:
    """Best-effort signal. Workflows reload state from Postgres, so a missed signal is recoverable."""
    try:
        client = await get_client()
        handle = client.get_workflow_handle(workflow_id)
        if arg is None:
            await handle.signal(signal_name)
        else:
            await handle.signal(signal_name, arg)
        return True
    except RPCError as exc:
        logger.info("signal %s to %s not delivered: %s", signal_name, workflow_id, exc.message)
        return False
    except Exception as exc:
        logger.warning("temporal unavailable for signal %s: %s", signal_name, exc)
        return False


async def health() -> bool:
    try:
        client = await get_client()
        await client.service_client.check_health()
        return True
    except Exception:
        return False
