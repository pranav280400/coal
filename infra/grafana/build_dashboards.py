"""Generates the provisioned Grafana dashboards (run: python infra/grafana/build_dashboards.py)."""

from __future__ import annotations

import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "cmg-prometheus"}
OUT = Path(__file__).parent / "dashboards"


def panel(pid: int, title: str, exprs: list[tuple[str, str]], x: int, y: int, w: int = 12, h: int = 8,
          kind: str = "timeseries", unit: str = "short") -> dict:
    return {
        "id": pid,
        "type": kind,
        "title": title,
        "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "fieldConfig": {"defaults": {"unit": unit}, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom"}} if kind == "timeseries" else
                   {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value"},
        "targets": [{"refId": chr(65 + i), "expr": e, "legendFormat": leg, "datasource": DS}
                    for i, (e, leg) in enumerate(exprs)],
    }


def row(pid: int, title: str, y: int) -> dict:
    return {"id": pid, "type": "row", "title": title, "collapsed": False, "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}}


def dashboard(uid: str, title: str, panels: list[dict]) -> dict:
    return {
        "uid": uid, "title": title, "tags": ["coalminegov"], "timezone": "browser", "schemaVersion": 39,
        "refresh": "30s", "time": {"from": "now-6h", "to": "now"}, "editable": False, "panels": panels,
    }


def platform() -> dict:
    p: list[dict] = []
    y = 0
    p.append(row(1, "Service health", y)); y += 1
    p.append(panel(2, "Targets up", [('sum by (job) (up)', "{{job}}")], 0, y, 8, 5, "stat"))
    p.append(panel(3, "API requests/s", [('sum(rate(cmg_http_requests_total[5m]))', "req/s")], 8, y, 8, 5, "stat", "reqps"))
    p.append(panel(4, "API 5xx ratio", [('sum(rate(cmg_http_requests_total{status=~"5.."}[5m])) / clamp_min(sum(rate(cmg_http_requests_total[5m])),1)', "5xx")], 16, y, 8, 5, "stat", "percentunit"))
    y += 5
    p.append(row(5, "API gateway", y)); y += 1
    p.append(panel(6, "Request rate by route", [('sum by (route) (rate(cmg_http_requests_total[5m]))', "{{route}}")], 0, y, 12, 8, unit="reqps"))
    p.append(panel(7, "Latency p50 / p95 / p99", [
        ('histogram_quantile(0.5, sum by (le) (rate(cmg_http_request_duration_seconds_bucket[5m])))', "p50"),
        ('histogram_quantile(0.95, sum by (le) (rate(cmg_http_request_duration_seconds_bucket[5m])))', "p95"),
        ('histogram_quantile(0.99, sum by (le) (rate(cmg_http_request_duration_seconds_bucket[5m])))', "p99"),
    ], 12, y, 12, 8, unit="s"))
    y += 8
    p.append(panel(8, "Responses by status", [('sum by (status) (rate(cmg_http_requests_total[5m]))', "{{status}}")], 0, y, 12, 7, unit="reqps"))
    p.append(panel(9, "In-flight requests", [('sum(cmg_http_requests_in_flight)', "in flight")], 12, y, 12, 7))
    y += 7
    p.append(row(10, "Event backbone (Kafka)", y)); y += 1
    p.append(panel(11, "Consumer group lag", [('sum by (consumergroup) (kafka_consumergroup_lag)', "{{consumergroup}}")], 0, y, 12, 8))
    p.append(panel(12, "Events consumed/s by consumer", [('sum by (consumer, outcome) (rate(cmg_events_consumed_total[5m]))', "{{consumer}} {{outcome}}")], 12, y, 12, 8))
    y += 8
    p.append(panel(13, "Events published/s by type", [('sum by (event_type) (rate(cmg_events_published_total[5m]))', "{{event_type}}")], 0, y, 12, 8))
    p.append(panel(14, "Outbox backlog / audit chain length", [('cmg_outbox_backlog', "outbox backlog"), ('cmg_audit_chain_length', "audit entries")], 12, y, 12, 8))
    y += 8
    p.append(row(15, "Workflows (Temporal)", y)); y += 1
    p.append(panel(16, "Workflows started/min", [('sum by (workflow) (rate(cmg_workflows_started_total[5m])) * 60', "{{workflow}}")], 0, y, 8, 8))
    p.append(panel(17, "Escalations", [('sum by (kind, level) (increase(cmg_escalations_total[1h]))', "{{kind}} L{{level}}")], 8, y, 8, 8))
    p.append(panel(18, "Workflow completions vs failures", [
        ('sum(rate(temporal_workflow_completed_total[5m]))', "completed (worker)"),
        ('sum(rate(temporal_workflow_failed_total[5m]))', "failed (worker)"),
        ('sum(rate(temporal_activity_execution_failed_total[5m]))', "activity failures"),
    ], 16, y, 8, 8))
    y += 8
    p.append(row(19, "AI layer", y)); y += 1
    p.append(panel(20, "LLM calls by operation/outcome", [('sum by (operation, outcome) (rate(cmg_llm_requests_total[5m]))', "{{operation}} {{outcome}}")], 0, y, 12, 8))
    p.append(panel(21, "LLM latency p95 by operation", [('histogram_quantile(0.95, sum by (le, operation) (rate(cmg_llm_request_duration_seconds_bucket[10m])))', "{{operation}}")], 12, y, 12, 8, unit="s"))
    y += 8
    p.append(panel(22, "OCR pages", [('sum by (outcome) (increase(cmg_ocr_pages_total[1h]))', "{{outcome}}")], 0, y, 8, 8))
    p.append(panel(23, "Notifications delivered", [('sum by (channel, outcome) (increase(cmg_notifications_sent_total[1h]))', "{{channel}} {{outcome}}")], 8, y, 8, 8))
    p.append(panel(24, "Mobile ingest events", [('sum by (event_type, outcome) (increase(cmg_ingest_events_total[1h]))', "{{event_type}} {{outcome}}")], 16, y, 8, 8))
    y += 8
    p.append(row(25, "Data stores", y)); y += 1
    p.append(panel(26, "Postgres connections", [('sum(pg_stat_activity_count)', "connections")], 0, y, 8, 7))
    p.append(panel(27, "Redis memory", [('redis_memory_used_bytes', "used")], 8, y, 8, 7, unit="bytes"))
    p.append(panel(28, "Redis ops/s", [('rate(redis_commands_processed_total[5m])', "ops/s")], 16, y, 8, 7))
    return dashboard("cmg-platform", "Lumen — Platform Health", p)


def governance() -> dict:
    p = [
        panel(1, "Mine compliance risk score (latest)", [('cmg_mine_risk_score', "{{mine_code}}")], 0, 0, 24, 10, "bargauge"),
        panel(2, "Risk score trend", [('cmg_mine_risk_score', "{{mine_code}}")], 0, 10, 12, 9),
        panel(3, "Escalations per hour", [('sum by (kind) (increase(cmg_escalations_total[1h]))', "{{kind}}")], 12, 10, 12, 9),
    ]
    return dashboard("cmg-governance", "Lumen — Governance Signals", p)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for d in (platform(), governance()):
        (OUT / f"{d['uid']}.json").write_text(json.dumps(d, indent=2), encoding="utf-8")
        print("wrote", d["uid"])
