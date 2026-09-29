"""Temporal worker process: runs workflows + activities and registers cron schedules."""

from __future__ import annotations

import asyncio
import logging
import signal
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    TLSConfig,
)
from temporalio.runtime import PrometheusConfig, Runtime, TelemetryConfig
from temporalio.worker import Worker

from app.ai import vectorstore
from app.core import storage
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workflows.activities import ALL_ACTIVITIES
from app.workflows.definitions import (
    ALL_WORKFLOWS,
    ComplianceSweepWorkflow,
    KnowledgeIndexWorkflow,
    RiskAnalyticsWorkflow,
    ScheduledReportsWorkflow,
)

logger = logging.getLogger("cmg.worker")


async def _connect() -> Client:
    s = get_settings()
    runtime = Runtime(
        telemetry=TelemetryConfig(metrics=PrometheusConfig(bind_address=f"0.0.0.0:{s.worker_metrics_port}"))
    )
    tls: TLSConfig | bool = False
    if s.temporal_tls_cert_path and s.temporal_tls_key_path:
        with open(s.temporal_tls_cert_path, "rb") as c, open(s.temporal_tls_key_path, "rb") as k:
            tls = TLSConfig(client_cert=c.read(), client_private_key=k.read())
    elif s.temporal_api_key:
        tls = True
    for attempt in range(30):
        try:
            return await Client.connect(
                s.temporal_host, namespace=s.temporal_namespace, tls=tls, runtime=runtime,
                api_key=s.temporal_api_key.get_secret_value() if s.temporal_api_key else None,
            )
        except Exception as exc:
            logger.warning("temporal not reachable (attempt %s): %s", attempt + 1, exc)
            await asyncio.sleep(min(2 + attempt, 10))
    raise RuntimeError("Could not connect to Temporal")


SCHEDULES = [
    # id, workflow, arg, cron (Asia/Kolkata)
    ("cmg-compliance-sweep", ComplianceSweepWorkflow.run, None, "30 0 * * *"),
    ("cmg-risk-analytics-daily", RiskAnalyticsWorkflow.run, {"train": False}, "0 2 * * *"),
    ("cmg-risk-model-training-weekly", RiskAnalyticsWorkflow.run, {"train": True}, "0 3 * * 0"),
    ("cmg-monthly-reports", ScheduledReportsWorkflow.run, None, "0 6 1 * *"),
    ("cmg-knowledge-index", KnowledgeIndexWorkflow.run, False, "0 1 * * *"),
]


async def ensure_schedules(client: Client) -> None:
    s = get_settings()
    for schedule_id, wf, arg, cron in SCHEDULES:
        action = ScheduleActionStartWorkflow(
            wf, *([] if arg is None else [arg]), id=f"{schedule_id}-run", task_queue=s.temporal_task_queue
        )
        schedule = Schedule(
            action=action,
            spec=ScheduleSpec(cron_expressions=[cron], time_zone_name=s.report_timezone),
            policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
        )
        try:
            await client.create_schedule(schedule_id, schedule)
            logger.info("created schedule %s (%s)", schedule_id, cron)
        except ScheduleAlreadyRunningError:
            pass


async def bootstrap(client: Client) -> None:
    """Idempotent start-up tasks: bucket, vector collection, initial knowledge index."""
    s = get_settings()
    try:
        await storage.ensure_bucket()
    except Exception as exc:
        logger.warning("object storage bootstrap failed: %s", exc)
    try:
        await vectorstore.ensure_collection()
    except Exception as exc:
        logger.warning("qdrant bootstrap failed: %s", exc)
    await ensure_schedules(client)
    try:
        await client.start_workflow(
            KnowledgeIndexWorkflow.run, False, id="cmg-knowledge-index-bootstrap", task_queue=s.temporal_task_queue
        )
    except Exception:
        pass  # already running / completed recently


async def main() -> None:
    configure_logging("worker")
    s = get_settings()
    client = await _connect()
    await bootstrap(client)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            pass
    # The pool must be at least as large as max_concurrent_activities, otherwise the SDK
    # warns and activities queue behind threads instead of running concurrently.
    max_activities = s.worker_max_concurrent_activities
    with ThreadPoolExecutor(max_workers=max_activities) as executor:
        worker = Worker(
            client,
            task_queue=s.temporal_task_queue,
            workflows=ALL_WORKFLOWS,
            activities=ALL_ACTIVITIES,
            activity_executor=executor,
            max_concurrent_activities=max_activities,
        )
        logger.info("temporal worker started on queue %s", s.temporal_task_queue)
        async with worker:
            await stop.wait()
    logger.info("temporal worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
