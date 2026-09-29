# Lumen — AI-Based Smart Governance & Compliance Monitoring System for Coal Mines

**Problem statement 26024 · Ministry of Coal / Coal India Limited · Smart Automation**

A centralised, AI-enabled governance platform for coal mining: statutory compliance tracking, geo-tagged field inspections (offline-first PWA), violation → corrective-action → verification workflows with automatic escalation, explainable risk scoring and anomaly detection, a multilingual RAG compliance assistant, OCR digitisation of legacy records, automated statutory reports, and a tamper-evident hash-chained audit trail. Role-based dashboards serve mine officials, corporate management, regulators and contractors.

> New here? Start with **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)** — a step-by-step first run that assumes no Docker experience.
> Every credential, provider by provider, plus production deployment: **[docs/CREDENTIALS_AND_SETUP.md](docs/CREDENTIALS_AND_SETUP.md)**

## Architecture

```
Browser / PWA (Next.js 16, offline queue in IndexedDB, service worker, web push)
   │  httpOnly-cookie session
   ▼
Next.js BFF (/api/auth/*, /api/proxy/* → token refresh, CSRF same-origin, SSE passthrough)
   │  Bearer JWT
   ▼
FastAPI gateway (RBAC + row-level tenant scoping, rate limiting, Prometheus metrics)
   │ writes state + domain event in ONE transaction (transactional outbox)
   ▼
PostgreSQL ──► outbox relay ──► Kafka  cmg.domain-events / cmg.field-events / cmg.dlq
                                   ├─► audit consumer         → hash-chained, write-once audit_log
                                   ├─► notification consumer  → in-app (Redis pub/sub → SSE), e-mail, SMS, web push
                                   ├─► analytics consumer     → dashboard cache invalidation (Redis)
                                   ├─► orchestrator consumer  → starts/signals Temporal workflows
                                   └─► ingest consumer        → materialises offline mobile events (idempotent)
Temporal worker: ViolationEscalation · ComplianceReminder · FieldIngestAgent (OCR→summary→hazards→embed→risk)
                 DocumentDigitization · ReportGeneration · scheduled sweeps, risk analytics, model retraining
AI: LiteLLM gateway → vLLM (chat + bge-m3 embeddings) · Qdrant (tenant-filtered RAG) · scikit-learn risk/anomaly
Object storage (S3/MinIO): photos, documents, reports, model artefacts · Prometheus + Grafana (ops)
```

## Requirement coverage

| Requirement | Implementation |
|---|---|
| FR1–3 Compliance CRUD, reminders, status rollups | `/compliance`, recurring obligations roll forward on completion; `ComplianceReminderWorkflow` (7/3/1-day reminders, overdue escalation, weekly re-escalation) |
| FR4 Geo-tagged mobile inspections, offline | PWA forms with GPS + camera, IndexedDB queue, idempotent `client_event_id`, `/ingest/events` → Kafka, geofence verification against lease polygon |
| FR5 AI-assisted, human-confirmed severity | LLM classifier grounded on Qdrant (regulations + past cases) with rules-engine fallback; confirmation required |
| FR6 Corrective-action workflow | assign → start → submit (evidence) → verify/reject (segregation of duties) → close; `ViolationEscalationWorkflow` with SLA-based L1→L3 escalation |
| FR7 Risk scoring | point-in-time features, class-balanced logistic regression (weekly retraining, AUC-gated activation) + explainable expert baseline; per-factor drivers |
| FR8 Anomaly detection | Poisson test vs. mine baseline for recurring violations, Isolation Forest operational outliers, attendance-drop detection |
| FR9–10 Semantic search, summaries, multilingual assistant | Qdrant + bge-m3; streaming RAG chat with citations in 7 Indian languages; inspection summaries |
| FR11 Contractor registry | compliance score, contracts/work orders, verification, encrypted PAN/contacts |
| FR12 Role-based dashboards | mine official · corporate (subsidiary or HQ) · regulator (read-only, cross-subsidiary) · contractor · admin |
| FR13 Scheduled statutory reports | Temporal schedule (monthly) + on-demand; PDF + Excel with AI executive summary and audit-head anchoring |
| FR14 OCR digitisation | Tesseract (English + Hindi) + PDF text layer → LLM field extraction → embeddings |
| FR15 Tamper-evident audit | SHA-256 hash chain built from Kafka events, DB trigger blocks UPDATE/DELETE, verification endpoint + CLI |
| Grievance redressal | `/grievances`: raise (optionally anonymous) → assign → start → resolve/reject → raiser confirms with a 1–5 rating or reopens; priority-based resolution deadline; `GrievanceSLAWorkflow` escalates L1→L3 each time it is missed |
| Production returns | `/production`: one monthly return per mine (target, produced, despatched, overburden, closing stock); FY achievement, 12-month trend, shortfall list; sharp drops and despatch > production raise operational anomalies |
| Environmental monitoring | `/environment`: PM10, PM2.5, SO₂, NO₂, day/night noise, effluent pH/TSS/oil & grease/COD checked against NAAQS 2009, Noise Rules 2000 and coal-mine effluent standards; a breach opens an environment violation automatically (`detected_by = system`) |
| Hindi / English interface | `EN / हि` switch on the landing page, login and app header; defaults to the user's profile language; shared UI components translate their own labels (`lib/i18n.tsx`, `lib/i18n-hi.ts`) |

## Repository layout

```
app/, components/, lib/, proxy.ts   Next.js web app + BFF (PWA: public/sw.js, app/manifest.ts)
backend/app/                        FastAPI services, domain services, AI, workflows, consumers
backend/migrations/                 Alembic migrations (incl. audit write-once trigger)
backend/tests/                      unit, Temporal workflow (time-skipping) and API integration tests
infra/                              LiteLLM, Prometheus (+alerts), Grafana dashboards, Keycloak test realm
scripts/                            bootstrap-env.{ps1,sh} — one-shot .env + secret generation
docker-compose.yml                  full stack (profiles: gpu = vLLM, sso = Keycloak)
docs/GETTING_STARTED.md             beginner-friendly first run
docs/CREDENTIALS_AND_SETUP.md       credentials, configuration, deployment
```

## Running

```bash
.\scripts\bootstrap-env.ps1     # Windows      — creates .env, generates every secret
./scripts/bootstrap-env.sh      # Linux/macOS  — same
docker compose up -d --build
docker compose ps                                       # wait for api + web = healthy
docker compose exec api python -m app.cli seed-demo     # optional demo data
```
Databases seeded before the grievance / production / environment modules existed can
add their demo data with `docker compose exec api python -m app.cli seed-operations`
(it only fills empty tables).
The bootstrap script is required: `docker compose` refuses to start with unset secrets
rather than leaving containers crash-looping on blank passwords.
Web: http://localhost:3000 · API docs: http://localhost:8000/docs · Temporal: :8233 · Grafana: :3001

Local development without Docker for the app tier:
```bash
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
python -m app.cli migrate && uvicorn app.main:app --reload         # API
python -m app.workflows.worker                                     # Temporal worker
python -m app.consumers.runner                                     # Kafka consumers + outbox relay
cd .. && pnpm install && pnpm dev                                  # web (API_INTERNAL_URL=http://localhost:8000)
```

## Tests

```bash
cd backend
pytest                                   # unit + Temporal workflow tests
TEST_DATABASE_URL=postgresql+asyncpg://user@localhost:5432/coalminegov_test pytest   # + API integration
cd .. && pnpm lint && pnpm build
```
Against the running compose stack (no local Python needed) — `PW` is `POSTGRES_PASSWORD` from `.env`:
```bash
docker compose exec -T postgres createdb -U cmg coalminegov_test
docker run --rm --user root --network coalminegov_default -v "$PWD/backend:/src:ro" -w /app \
  -e ENVIRONMENT=test -e "TEST_DATABASE_URL=postgresql+asyncpg://cmg:$PW@postgres:5432/coalminegov_test" \
  coalminegov/backend:1.0.0 sh -c "pip install -q pytest pytest-asyncio fakeredis; cp -r /src/tests /app/tests; cp /src/pyproject.toml /src/alembic.ini /app/; python -m pytest -q"
```

## Security highlights

Argon2id passwords · 15-min JWT + rotating refresh tokens with reuse detection · httpOnly/SameSite cookies, same-origin CSRF checks · Redis rate limiting and login lockout · RBAC + row-level tenancy on every query and in vector search · Fernet field encryption for PII with key rotation · magic-byte upload validation · strict security headers/CSP · write-once hash-chained audit log · production start-up guard against default secrets.
