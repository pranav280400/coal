"""Prometheus metrics shared by API, workers and consumers."""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge, Histogram
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS = Counter(
    "cmg_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "cmg_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
HTTP_IN_FLIGHT = Gauge("cmg_http_requests_in_flight", "In-flight HTTP requests")

EVENTS_PUBLISHED = Counter("cmg_events_published_total", "Events published to Kafka", ["topic", "event_type"])
EVENTS_CONSUMED = Counter(
    "cmg_events_consumed_total", "Events consumed from Kafka", ["consumer", "event_type", "outcome"]
)
OUTBOX_BACKLOG = Gauge("cmg_outbox_backlog", "Unpublished outbox rows")
AUDIT_CHAIN_LENGTH = Gauge("cmg_audit_chain_length", "Number of entries in the audit hash chain")

WORKFLOWS_STARTED = Counter("cmg_workflows_started_total", "Temporal workflows started", ["workflow"])
ESCALATIONS = Counter("cmg_escalations_total", "Violation/compliance escalations", ["kind", "level"])
NOTIFICATIONS_SENT = Counter("cmg_notifications_sent_total", "Notifications delivered", ["channel", "outcome"])

LLM_REQUESTS = Counter("cmg_llm_requests_total", "LLM gateway requests", ["operation", "outcome"])
LLM_LATENCY = Histogram(
    "cmg_llm_request_duration_seconds",
    "LLM gateway latency",
    ["operation"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 80, 160),
)
OCR_PAGES = Counter("cmg_ocr_pages_total", "Pages processed by OCR", ["outcome"])
RISK_SCORE = Gauge("cmg_mine_risk_score", "Latest compliance risk score per mine", ["mine_code"])
INGEST_EVENTS = Counter("cmg_ingest_events_total", "Mobile/offline events ingested", ["event_type", "outcome"])


def _route_template(request: Request) -> str:
    """Low-cardinality label: the matched route template (set in scope by the router)."""
    route = request.scope.get("route")
    path = getattr(route, "path_format", None) or getattr(route, "path", None)
    if path:
        prefix = request.scope.get("root_path", "")
        return path if path.startswith("/api") or not prefix else prefix + path
    return "unmatched"


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/metrics":
            return await call_next(request)
        HTTP_IN_FLIGHT.inc()
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            HTTP_IN_FLIGHT.dec()
            route = _route_template(request)
            HTTP_LATENCY.labels(request.method, route).observe(time.perf_counter() - start)
            HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
