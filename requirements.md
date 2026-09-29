# AI-Based Smart Governance & Compliance Monitoring System for Coal Mines

### Requirements & Architecture Document — PS 26024 (SIH 2026)

---

## 1. Tech Stack — What Each Piece Does

| Tech | Role in this project |
| --- | --- |
| **Next.js** | Web frontend — dashboards for mine officials, corporate management, regulators. Server-side rendering for fast dashboard loads, API routes for BFF (backend-for-frontend) needs. |
| **FastAPI** | Core backend services — compliance API, inspection API, contractor API, auth, report generation. Async, fast, typed, plays well with Pydantic for statutory-form validation. |
| **PostgreSQL** | System of record — compliance records, inspections, violations, contractors, users, audit logs. Relational integrity matters here (regulatory data, legal traceability). |
| **Redis** | Caching (dashboard queries, session/auth tokens), rate limiting, pub/sub for real-time alert delivery, Celery/Temporal task queues backing store. |
| **Kafka** | Event backbone — every field event (inspection submitted, violation flagged, attendance logged) is a Kafka event. Decouples mobile ingestion from AI processing, dashboard updates, and audit-trail writing. Enables replay and multi-consumer fan-out (analytics engine + audit log + notification service all read the same stream). |
| **Qdrant (Vector DB)** | Stores embeddings of regulation text, past violation reports, inspection notes → powers semantic search ("find similar past violations"), RAG for the compliance-assistant chatbot, and anomaly matching (is this new report similar to a known risk pattern?). |
| **LiteLLM** | Unified LLM gateway — lets your AI services call any underlying model (vLLM-hosted or otherwise) through one OpenAI-compatible interface. Simplifies swapping/routing models for different tasks (summarization, classification, multilingual chat). |
| **vLLM** | High-throughput local inference server for your LLM — used for report summarization, OCR-text cleanup, multilingual query handling, and generating natural-language compliance report drafts. |
| **Temporal** | Orchestrates long-running, multi-step, stateful workflows: an inspection → violation → escalation → corrective-action → re-inspection cycle can take days/weeks and involves retries, human approval steps, and timeouts. Temporal manages this reliably (durable execution) instead of hand-rolled cron/queue logic. Also used to orchestrate multi-step AI agent pipelines (ingest → OCR → embed → classify → alert). |
| **Docker Compose** | Local/dev orchestration of Postgres, Redis, Kafka, Qdrant, Temporal server — one command to spin up the full backing-services stack. |
| **Prometheus** | Metrics collection — scrapes FastAPI services, Kafka, Postgres/Redis exporters, and Temporal for request rates, latencies, queue depths, workflow failures. Gives you the numbers behind "system health" for a governance platform that itself needs to be auditable. |
| **Grafana** | Visualizes Prometheus metrics — ops dashboards (service uptime, Kafka lag, Temporal workflow success/failure rates) separate from the business dashboards in Next.js. Strong demo value: shows judges the platform monitors itself, which fits the "transparency and accountability" theme of the PS. |

**Why this stack fits the PS:** the problem statement explicitly asks for AI/analytics-driven risk detection, geo-tagged mobile reporting at scale, automated workflows/escalations, and multi-tenant dashboards — this maps directly to Kafka (ingestion scale) + Temporal (workflow/escalation logic) + Qdrant/LiteLLM/vLLM (the AI layer) + Postgres (compliance system of record).

---

## 2. High-Level Architecture

```
                     ┌─────────────────────────┐
                     │   Next.js Web Dashboard  │
                     │ (Mine / Corporate / Reg) │
                     └────────────┬─────────────┘
                                  │ REST/GraphQL
                     ┌────────────▼─────────────┐
                     │      FastAPI Gateway      │
                     │  (auth, routing, BFF)     │
                     └───┬───────┬────────┬──────┘
                         │       │        │
        ┌────────────────┘   ┌──┘        └──────────────┐
        ▼                    ▼                            ▼
┌───────────────┐   ┌─────────────────┐         ┌──────────────────┐
│ Compliance Svc │   │  Inspection Svc  │         │ Contractor Svc    │
│   (FastAPI)    │   │    (FastAPI)     │         │   (FastAPI)       │
└───────┬────────┘   └────────┬─────────┘         └─────────┬────────┘
        │                     │                              │
        └──────────┬──────────┴──────────────┬───────────────┘
                    ▼                         ▼
             ┌─────────────┐          ┌───────────────┐
             │  PostgreSQL │          │     Kafka      │◄──── Mobile App
             │ (system of  │          │ (event bus:    │      (geo-tagged,
             │  record)    │          │ inspections,   │       offline-sync
             └─────────────┘          │ violations,    │       reports)
                                       │ attendance)    │
                                       └───────┬────────┘
                          ┌────────────────────┼────────────────────┐
                          ▼                    ▼                    ▼
                 ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
                 │  AI/Analytics   │   │  Audit-Trail    │   │  Notification   │
                 │    Consumer     │   │    Consumer     │   │    Consumer     │
                 │ (risk scoring,  │   │ (immutable log  │   │ (alerts/email/  │
                 │  anomaly detect)│   │  writer)        │   │  SMS/push)      │
                 └───────┬────────┘   └────────┬────────┘   └────────────────┘
                         │                     │
             ┌───────────┼──────────┐          ▼
             ▼           ▼          ▼    ┌───────────┐
       ┌─────────┐ ┌──────────┐ ┌──────┐ │ PostgreSQL │
       │ Qdrant  │ │ LiteLLM  │ │ vLLM │ │(audit_logs)│
       │(vectors)│ │(gateway) │ │(infer)│ └───────────┘
       └─────────┘ └──────────┘ └──────┘

             ┌─────────────────────────────────────┐
             │        Temporal Workflow Engine       │
             │ orchestrates: inspection→violation→  │
             │ escalation→corrective-action→re-check │
             │ and multi-step AI agent pipelines     │
             └─────────────────────────────────────┘
                 (Temporal workers hook into FastAPI
                  services + AI consumers above)

              Redis: caching, session store, Temporal/
              Kafka-consumer backing state, rate limits
```

---

## 3. Functional Requirements (mapped to PS asks)

### 3.1 Compliance Management

- FR1: CRUD for statutory compliance items (safety, environment, production, labour) per mine site.
- FR2: Compliance due-date tracking with automated reminders (Temporal timers → Notification Consumer).
- FR3: Compliance status dashboard (compliant / due / overdue / violated) per mine and rolled up corporate-wide.

### 3.2 Inspection & Violation Tracking

- FR4: Mobile app to log inspections with geo-tag + timestamp + photo evidence, offline-capable with sync-on-reconnect.
- FR5: Violation flagging with severity classification (AI-assisted, human-confirmed).
- FR6: Corrective Action workflow: violation → assigned action → deadline → verification → close (Temporal workflow).

### 3.3 AI/Analytics Engine

- FR7: Risk-scoring model that ranks mine sites/contractors by compliance-risk using historical violation data.
- FR8: Anomaly detection on recurring violation patterns (same site/type repeating beyond threshold).
- FR9: Semantic search over past inspection reports and regulation text (Qdrant + embeddings).
- FR10: LLM-generated report summaries and multilingual query assistant (LiteLLM → vLLM), grounded via RAG over Qdrant.

### 3.4 Contractor Management

- FR11: Contractor registry with compliance score, active contracts, past violations.

### 3.5 Dashboards & Reporting

- FR12: Role-based dashboards — Mine Official (site-level), Corporate (multi-site rollup), Regulator (read-only, cross-subsidiary).
- FR13: Auto-generated statutory reports (PDF/Excel export) on schedule (Temporal cron workflows).

### 3.6 Document Digitization

- FR14: OCR ingestion pipeline for legacy paper records → structured data + embeddings into Qdrant.

### 3.7 Audit Trail

- FR15: Immutable, timestamped log of every state change (who/what/when), sourced directly from the Kafka event stream — optionally hash-chained for tamper-evidence (blockchain-style audit trail without needing a full blockchain).

---

## 4. Non-Functional Requirements

- **Scalability:** stateless FastAPI services behind a load balancer; Kafka partitioned by mine-site ID so throughput scales horizontally as more mines onboard.
- **Offline resilience:** mobile app queues events locally, syncs to Kafka ingestion endpoint on reconnect (idempotent event IDs to prevent duplicates).
- **Data integrity:** Postgres as system of record; Kafka topics retained long enough to replay into Postgres/audit log if a consumer fails.
- **Multi-tenancy:** every table/event partitioned by `subsidiary_id` / `mine_site_id`; row-level access control enforced at the FastAPI gateway.
- **Security:** RBAC (mine official / corporate / regulator / contractor), JWT auth, encrypted PII, audit log write-once.
- **Latency:** dashboard reads served from cached aggregates (Redis) refreshed by consumers, not computed on-the-fly from raw event stream.

---

## 5. Core Data Model (Postgres, simplified)

```
mines(id, name, subsidiary_id, location_geo, ...)
compliance_items(id, mine_id, category, regulation_ref, due_date, status)
inspections(id, mine_id, inspector_id, geo_lat, geo_lng, timestamp, notes, media_refs)
violations(id, inspection_id, severity, status, risk_score, detected_by [ai|human])
corrective_actions(id, violation_id, assigned_to, deadline, status, verified_by)
contractors(id, name, subsidiary_id, compliance_score, active_contracts)
audit_log(id, entity_type, entity_id, actor_id, action, before, after, ts, prev_hash, hash)
users(id, role, mine_id/subsidiary_id, ...)
```

---

## 6. Temporal Workflow Examples

1. **`ComplianceReminderWorkflow`** — runs per compliance item; sleeps until N days before due date, sends reminder, escalates to corporate if still open past due date.
2. **`ViolationEscalationWorkflow`** — starts when a violation is flagged; waits for corrective action assignment (timeout → auto-escalate), waits for verification, closes or re-escalates.
3. **`FieldIngestAgentWorkflow`** — triggered per inspection event: OCR (if scanned doc attached) → embed into Qdrant → call risk-scoring model via LiteLLM/vLLM → write result → publish alert if high-risk.
4. **`ReportGenerationWorkflow`** — scheduled (cron) per mine/subsidiary, aggregates data, calls vLLM for a natural-language summary, renders PDF, delivers to regulator dashboard.

Temporal is the right fit here specifically because these are **long-running, multi-actor, retry-heavy** processes — exactly what a demo needs to look "production-grade" rather than a toy CRUD app.

---

## 7. Docker Compose Scope (dev environment)

Services to containerize:

- `postgres` (with init SQL for the schema above)
- `redis`
- `kafka` + `zookeeper` (or KRaft mode, no zookeeper)
- `qdrant`
- `temporal` (server + UI, `temporalite` or official docker-compose from Temporal repo)
- `prometheus` (scrape config targeting FastAPI `/metrics`, `postgres_exporter`, `redis_exporter`, `kafka_exporter`, Temporal metrics endpoint)
- `grafana` (provisioned with a Prometheus datasource + starter dashboards for service latency, Kafka consumer lag, Temporal workflow status)

FastAPI services, Next.js frontend, and the LiteLLM/vLLM inference layer (already available per your note) run separately or are added to the same compose file as app-tier services once built.

---

## 8. Suggested Build Order (for hackathon timeline)

1. Postgres schema + FastAPI CRUD for compliance/inspection/contractor (core skeleton, demoable early).
2. Kafka event pipeline: mobile → ingestion endpoint → topic → simple consumer writing to Postgres.
3. Next.js dashboard reading from Postgres (role-based views).
4. Temporal: wire the `ComplianceReminderWorkflow` and `ViolationEscalationWorkflow` — this is your "wow, it's automated" demo moment.
5. AI layer: Qdrant embeddings + LiteLLM/vLLM risk-scoring and RAG chatbot — layer in last, since it's the highest-effort/highest-payoff piece for judges.
6. Mobile geo-tagged reporting (can be a lightweight PWA if a native app is too costly in the time available).

---
