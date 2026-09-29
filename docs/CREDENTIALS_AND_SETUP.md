# Lumen — Credentials, Configuration & Deployment Guide

This guide lists **every credential and configuration value** the platform needs, explains **how to obtain each one**, and shows **how to provide it securely** for local development and production. All configuration is read from environment variables (12-factor); the single template is [`.env.example`](../.env.example).

> **Golden rules**
> 1. Never commit `.env` or any key/cert file (both are git-ignored).
> 2. Generate secrets with a CSPRNG — use `python -m app.cli generate-secrets` (see §2).
> 3. In production, inject secrets from a secret manager (Vault, AWS Secrets Manager, Azure Key Vault, Kubernetes Secrets, Docker secrets) — not from files on disk.
> 4. With `ENVIRONMENT=production` the backend **refuses to start** if any secret still has a development default, if `DEBUG` is on, or if CORS origins are not HTTPS.

---

## 0. What you need to provide — at a glance

| # | Item | Required? | Who issues it | Env vars |
|---|------|-----------|---------------|----------|
| 1 | Application secrets (JWT, PII encryption key, service passwords) | **Yes** | You — generated locally | `JWT_SECRET_KEY`, `PII_ENCRYPTION_KEY`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `QDRANT_API_KEY`, `S3_SECRET_ACCESS_KEY`, `GRAFANA_ADMIN_PASSWORD` |
| 2 | First administrator account | **Yes** (first deploy) | You | `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` |
| 3 | LLM inference endpoint (vLLM) | **Yes** for AI features | Your GPU server / existing vLLM | `VLLM_CHAT_API_BASE`, `VLLM_EMBED_API_BASE`, `VLLM_API_KEY`, `LLM_API_KEY` |
| 4 | Hugging Face token | Only for gated models | huggingface.co | `HF_TOKEN` |
| 5 | Production PostgreSQL | **Yes** (prod) | Managed DB or DBA | `DATABASE_URL` |
| 6 | Production Redis | **Yes** (prod) | Managed Redis or ops | `REDIS_URL` |
| 7 | Production Kafka | **Yes** (prod) | Managed Kafka or ops | `KAFKA_*` |
| 8 | Qdrant (vector DB) | **Yes** | Self-host or Qdrant Cloud | `QDRANT_URL`, `QDRANT_API_KEY` |
| 9 | Temporal | **Yes** | Self-host or Temporal Cloud | `TEMPORAL_*` |
| 10 | Object storage (S3-compatible) | **Yes** | AWS S3 / NIC cloud / MinIO | `S3_*` |
| 11 | SMTP e-mail relay | Recommended | NIC SMTP / AWS SES / SendGrid | `SMTP_*`, `EMAIL_ENABLED` |
| 12 | SMS gateway + DLT registration | Optional (critical alerts) | MSG91 or Twilio + TRAI DLT | `SMS_PROVIDER`, `MSG91_*`/`TWILIO_*` |
| 13 | Government SSO (OIDC client) | Optional | NIC (Parichay/MeriPehchaan) or your IdP | `SSO_*` |
| 14 | Web-push VAPID keys | Optional | You — generated locally | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` |
| 15 | Map tile provider | Recommended (prod) | MapTiler / self-hosted / Bhuvan / MapmyIndia | `NEXT_PUBLIC_MAP_TILE_URL`, `NEXT_PUBLIC_MAP_ATTRIBUTION` |
| 16 | TLS certificate + domain | **Yes** (prod) | CA / NIC / Let's Encrypt | reverse proxy config |

**Minimum to run locally:** items 1–3 (item 3 can be any OpenAI-compatible endpoint; everything except AI works without it). Everything else runs inside Docker Compose.

---

## 1. Local quick start (Docker Compose)

Prerequisites: Docker Desktop ≥ 4.30 (Compose v2), 16 GB RAM recommended; an NVIDIA GPU only if you want to run vLLM locally. Never used Docker before? Follow [GETTING_STARTED.md](GETTING_STARTED.md) instead — same result, more hand-holding.

> **Host ports.** Every published port is settable in `.env` (`POSTGRES_HOST_PORT`, `WEB_HOST_PORT`, …). If a service fails with `ports are not available … bind: … forbidden by its access permissions`, something else on the machine owns that port — a locally installed PostgreSQL on 5432 is the usual culprit. Change the variable, not the compose file.

```bash
.\scripts\bootstrap-env.ps1     # Windows
./scripts/bootstrap-env.sh      # Linux/macOS
```

That one command creates `.env` from the template, generates every required secret inside
the backend container image (no local Python needed) and prompts for the first
administrator's e-mail and password. It is idempotent — re-running never overwrites a value
you have already set. Only the vLLM endpoint (§6) is left for you to fill in, and the
platform runs without it.

> `docker compose` now **refuses to start** if a required secret is missing, naming the
> variable, instead of leaving Postgres or MinIO crash-looping on a blank password.

Start everything:

```bash
docker compose up -d --build                  # add --profile gpu to also run vLLM locally
docker compose exec api python -m app.cli seed-demo   # optional demo data (21 CIL mines, 1 year history)
```

| URL | Service |
|-----|---------|
| http://localhost:3000 | Web app (dashboards, PWA) |
| http://localhost:8000/docs | API (OpenAPI; disabled in production) |
| http://localhost:8233 | Temporal UI (workflows) |
| http://localhost:3001 | Grafana (ops dashboards) |
| http://localhost:9090 | Prometheus |
| http://localhost:9001 | MinIO console |
| http://localhost:4000 | LiteLLM gateway |

Demo accounts (only after `seed-demo`, password `CoalMine@2026`): `ravi.kumar` (mine official), `suresh.patnaik` (MCL corporate), `anita.sharma` (CIL HQ), `dgms.regulator` (regulator), `contractor.demo` (contractor), `admin`. **Never seed demo data in production** (the CLI refuses unless `--force`).

---

## 2. Application secrets (generate yourself)

Run once per environment (dev, staging and production must all differ):

```bash
cd backend && python -m app.cli generate-secrets
```

It prints cryptographically random values for:

| Variable | Purpose | Format / rules |
|----------|---------|----------------|
| `JWT_SECRET_KEY` | Signs 15-minute access tokens (HS256) | ≥ 32 chars (generator gives 86) |
| `PII_ENCRYPTION_KEY` | Fernet (AES-128-CBC + HMAC-SHA256) key encrypting phone numbers, PAN, contractor contacts, worker IDs at rest | 32-byte url-safe base64 |
| `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `QDRANT_API_KEY`, `S3_SECRET_ACCESS_KEY`, `GRAFANA_ADMIN_PASSWORD` | Service credentials for the compose stack | random url-safe |
| `LLM_API_KEY` | LiteLLM master key; backend authenticates to the gateway with it | `sk-…` |
| `VLLM_API_KEY` | Key vLLM enforces (`--api-key`) | random |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | Web-push signing (P-256) | raw url-safe base64 |

**Rotation**
* `JWT_SECRET_KEY`: replacing it signs everyone out (access tokens become invalid; refresh tokens are opaque and survive, so users are silently re-issued tokens). Rotate at least yearly or on suspicion.
* `PII_ENCRYPTION_KEY`: supports **zero-downtime rotation** — set `PII_ENCRYPTION_KEY=<new>,<old>`; new writes use the first key, reads try all. Re-save records (or run a re-encryption job) then drop the old key.
* Service passwords: change in the service and in the secret store, then restart the app tier.

---

## 3. First administrator

Set before the first `migrate`:

```env
BOOTSTRAP_ADMIN_EMAIL=it-admin@your-domain.gov.in
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=<strong password>
```

`python -m app.cli migrate` (run automatically by the `migrate` compose service) creates the account only if no administrator exists. Sign in, change the password under **Settings → Security**, then **remove `BOOTSTRAP_ADMIN_PASSWORD` from the environment**. Additional admins: **Users & Access → Add user**, or `python -m app.cli create-admin --username … --email …` (prompts for the password).

---

## 4. PostgreSQL (system of record)

**Local:** provided by compose (`postgres:16`). Only `POSTGRES_PASSWORD` is needed.

**Production options:** AWS RDS/Aurora PostgreSQL, Azure Database for PostgreSQL, a MeitY-empanelled cloud (e.g. NIC MeghRaj), or a self-managed HA cluster (Patroni). PostgreSQL ≥ 14.

1. Create a database `coalminegov` and **two roles**:
   ```sql
   CREATE ROLE cmg_migrator LOGIN PASSWORD '…';            -- owns schema, runs Alembic
   CREATE ROLE cmg_app LOGIN PASSWORD '…';                 -- runtime (API, worker, consumers)
   GRANT CONNECT ON DATABASE coalminegov TO cmg_app;
   ALTER DEFAULT PRIVILEGES FOR ROLE cmg_migrator IN SCHEMA public
     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cmg_app;
   ALTER DEFAULT PRIVILEGES FOR ROLE cmg_migrator IN SCHEMA public
     GRANT USAGE, SELECT ON SEQUENCES TO cmg_app;
   ```
   The `audit_log` table is additionally protected by a trigger that rejects UPDATE/DELETE/TRUNCATE for every role.
2. Temporal needs its own databases (`temporal`, `temporal_visibility`) — use a separate instance or role in production.
3. Connection string (asyncpg driver, TLS enforced):
   ```env
   DATABASE_URL=postgresql+asyncpg://cmg_app:<password>@db.internal:5432/coalminegov?ssl=require
   ```
   Run migrations with the migrator role: `DATABASE_URL=…cmg_migrator… python -m app.cli migrate`.
4. Enable automated backups + PITR (WAL archiving), 35-day retention; test restores quarterly.

---

## 5. Redis (cache, sessions, rate limits, real-time fan-out)

**Local:** compose; set `REDIS_PASSWORD`.

**Production:** AWS ElastiCache / Azure Cache for Redis / self-hosted Redis 7 with `requirepass` + TLS. Redis holds refresh-token families, lockout counters, rate-limit windows, dashboard caches and pub/sub for live notifications — enable persistence (AOF) and `maxmemory-policy noeviction`.

```env
REDIS_URL=rediss://:<password>@redis.internal:6380/0     # rediss = TLS
```

---

## 6. AI layer — vLLM + LiteLLM (+ optional Hugging Face token)

The backend only knows two logical model names, `cmg-chat` and `cmg-embed`, served through **LiteLLM** (`infra/litellm/config.yaml`), which forwards to **vLLM**.

### 6.1 If you already have vLLM servers
Provide:
```env
VLLM_CHAT_API_BASE=https://vllm-chat.internal/v1     # OpenAI-compatible base URL
VLLM_EMBED_API_BASE=https://vllm-embed.internal/v1
VLLM_API_KEY=<the --api-key your vLLM enforces>
```
Requirements: the chat server must expose an instruction-tuned, multilingual model under served name `cmg-chat` (e.g. `Qwen/Qwen2.5-7B-Instruct`, `meta-llama/Llama-3.1-8B-Instruct`); the embedding server a multilingual embedding model under `cmg-embed` (recommended `BAAI/bge-m3`, **1024 dimensions**). If you use a different embedding model, set `EMBEDDING_DIM` to its dimension **before** the first run (the Qdrant collection is created with that size).

### 6.2 Running vLLM with this repo (`--profile gpu`)
* Hardware: NVIDIA GPU with ≥ 24 GB VRAM (L4, A10G, RTX 4090, A100) for a 7–8B model + bge-m3; NVIDIA driver + **nvidia-container-toolkit**.
* `HF_TOKEN`: only needed for gated models (e.g. Llama). Create at https://huggingface.co/settings/tokens (type *Read*), accept the model licence on its model page, then set `HF_TOKEN=hf_…`.
* `docker compose --profile gpu up -d` downloads the weights into the `hfcache` volume on first start (≈16 GB).

### 6.3 LiteLLM gateway
* `LLM_API_KEY` is LiteLLM's master key (`LITELLM_MASTER_KEY`); the backend sends it as a bearer token. For per-service keys and spend tracking, attach a PostgreSQL database to LiteLLM and create virtual keys (see LiteLLM docs) — then set `LLM_API_KEY` to the virtual key.
* Optional cloud fallback when the GPU is down: uncomment the fallback block in `infra/litellm/config.yaml` and provide that provider's key (e.g. `OPENAI_API_KEY`). **Check data-residency policy before sending government data to any external provider.**

### 6.4 Verify
```bash
curl -H "Authorization: Bearer $LLM_API_KEY" http://localhost:4000/v1/models
curl -H "Authorization: Bearer $LLM_API_KEY" http://localhost:4000/v1/embeddings -H 'Content-Type: application/json' \
     -d '{"model":"cmg-embed","input":["test"]}' | python -c "import json,sys;print(len(json.load(sys.stdin)['data'][0]['embedding']))"   # → 1024
```
In the app: **AI Assistant** answers with citations; `/api/v1/ai/status` reports gateway and vector-store health.

*Without an LLM*, everything else keeps working: severity suggestions fall back to a transparent rules engine (marked "rules"), risk scoring and anomaly detection are local scikit-learn models, and OCR still extracts text (AI structuring/indexing resumes when the gateway is back).

---

## 7. Kafka (event backbone)

**Local:** compose runs Apache Kafka 3.9 in KRaft mode (no ZooKeeper); topics are created by the consumers on start.

**Production:** Amazon MSK, Confluent Cloud, Aiven, or Strimzi on Kubernetes (3 brokers). Create topics (or let the app create them with `KAFKA_REPLICATION_FACTOR=3`):

| Topic | Partitions | Retention | Key |
|-------|-----------|-----------|-----|
| `cmg.domain-events` | 12+ | 90 days | mine id |
| `cmg.field-events` | 12+ | 30 days | mine id |
| `cmg.dlq` | 3 | 180 days | event id |

Credentials (SASL/SCRAM over TLS example):
```env
KAFKA_BOOTSTRAP_SERVERS=b-1.kafka.internal:9096,b-2.kafka.internal:9096
KAFKA_SECURITY_PROTOCOL=SASL_SSL
KAFKA_SASL_MECHANISM=SCRAM-SHA-512
KAFKA_SASL_USERNAME=cmg-app
KAFKA_SASL_PASSWORD=<password>
KAFKA_SSL_CAFILE=/run/secrets/kafka-ca.pem     # if the broker CA is private
```
ACLs for `cmg-app`: produce + consume on the three topics; consumer groups `cmg-audit`, `cmg-notifications`, `cmg-analytics`, `cmg-orchestrator`, `cmg-ingest`.

---

## 8. Qdrant (vector database)

**Local:** compose; `QDRANT_API_KEY` secures it.
**Qdrant Cloud:** create a cluster at https://cloud.qdrant.io → *Data Access Control* → create an API key.
```env
QDRANT_URL=https://<cluster-id>.<region>.cloud.qdrant.io:6333
QDRANT_API_KEY=<key>
```
The collection `cmg_knowledge` (size `EMBEDDING_DIM`, cosine) and its payload indexes are created automatically by the worker. Regulations are embedded at startup and nightly; inspections, violations and documents as they arrive. Tenant isolation is enforced with payload filters (`mine_id`, `subsidiary_id`, `public`).

---

## 9. Temporal (durable workflows)

**Local:** compose (`temporalio/auto-setup`) + UI on :8233. No credentials.

**Temporal Cloud (recommended for production):**
1. Create a namespace at https://cloud.temporal.io (e.g. `coalminegov-prod.<account>`), region `ap-south-1` if data residency requires.
2. Authentication — choose one:
   * **mTLS**: generate a CA and client cert (`tcld gen ca` / your PKI), upload the CA to the namespace, then mount the client cert/key into the worker/API/consumer containers:
     ```env
     TEMPORAL_HOST=coalminegov-prod.<account>.tmprl.cloud:7233
     TEMPORAL_NAMESPACE=coalminegov-prod.<account>
     TEMPORAL_TLS_CERT_PATH=/run/secrets/temporal-client.pem
     TEMPORAL_TLS_KEY_PATH=/run/secrets/temporal-client.key
     ```
   * **API key**: create a service account + API key in the Cloud UI, then set `TEMPORAL_HOST` to the namespace's API-key endpoint shown in the UI and `TEMPORAL_API_KEY=<key>`.
**Self-hosted:** deploy the official Temporal Helm chart with PostgreSQL persistence and TLS; set `TEMPORAL_HOST` accordingly.

The worker registers these schedules idempotently on start (times in `REPORT_TIMEZONE`): compliance sweep 00:30 daily, risk analytics 02:00 daily, model retraining Sunday 03:00, monthly reports 1st 06:00, knowledge re-index 01:00.

---

## 10. Object storage (photos, documents, reports, ML models)

**Local:** MinIO in compose (`S3_ACCESS_KEY_ID` = root user, `S3_SECRET_ACCESS_KEY` = root password, ≥ 8 chars). Console at :9001.

**AWS S3 (production):**
1. Create bucket `coalminegov-files-prod` in `ap-south-1`, *Block all public access* ON, default encryption SSE-S3 (or SSE-KMS), versioning ON, lifecycle rules as per record-retention policy.
2. Create an IAM user/role with **only** this policy:
   ```json
   {"Version":"2012-10-17","Statement":[
     {"Effect":"Allow","Action":["s3:PutObject","s3:GetObject","s3:DeleteObject"],"Resource":"arn:aws:s3:::coalminegov-files-prod/*"},
     {"Effect":"Allow","Action":["s3:ListBucket","s3:GetBucketLocation"],"Resource":"arn:aws:s3:::coalminegov-files-prod"}]}
   ```
3. Configure (prefer an instance/task role over static keys where possible):
   ```env
   S3_ENDPOINT_URL=                      # empty = AWS
   S3_PUBLIC_ENDPOINT_URL=
   S3_REGION=ap-south-1
   S3_BUCKET=coalminegov-files-prod
   S3_ACCESS_KEY_ID=AKIA…
   S3_SECRET_ACCESS_KEY=…
   S3_FORCE_PATH_STYLE=false
   ```
**Other S3-compatible stores** (NIC cloud object storage, Ceph RGW, MinIO cluster): set `S3_ENDPOINT_URL` to the internal endpoint and `S3_PUBLIC_ENDPOINT_URL` to the hostname browsers can reach (pre-signed download URLs are signed for that host; they expire after `S3_PRESIGN_TTL_SECONDS`, default 15 min).

> Note: MinIO withdrew its community images from Docker Hub, so compose pulls the last
> published release from **quay.io** (`quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z`). For production use AWS S3, a supported MinIO AIStor subscription, Ceph, or another S3-compatible service.

---

## 11. E-mail (SMTP)

Used for password resets, escalations, reminders and report notifications.

* **NIC e-mail relay** (government domains): request an SMTP relay account through your NIC coordinator; you receive host, port (typically 587/465), username and password.
* **AWS SES**: verify your domain (DKIM records), request production access, create SMTP credentials (SES console → *SMTP settings*).
* **SendGrid / others**: create an API key with *Mail Send*; SMTP username is `apikey`.

```env
EMAIL_ENABLED=true
SMTP_HOST=email-smtp.ap-south-1.amazonaws.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_USERNAME=<smtp user>
SMTP_PASSWORD=<smtp password>
SMTP_FROM=Lumen <no-reply@your-domain.gov.in>
```
Publish SPF, DKIM and DMARC records for the sender domain. Test delivery with `POST /api/v1/notifications/test?channel=email` (signed in), or trigger **Forgot password** for your own account.

---

## 12. SMS (critical alerts & escalations)

In India, commercial SMS requires **TRAI DLT registration** (TCCCPR 2018):
1. Register your organisation as a *Principal Entity* on a DLT portal (e.g. Jio, Airtel, Vi, BSNL — one registration works across operators).
2. Register a **Sender ID (header)**, e.g. `CMGOVT`.
3. Register a **content template** (transactional/service-implicit), e.g.
   `Lumen: {#var#}` — note the DLT template ID.

**MSG91** (`SMS_PROVIDER=msg91`): create an account at https://msg91.com, link your DLT entity/header, create a *Flow* whose template text maps to the DLT template and contains the variable `##message##`, and copy the Auth Key and the Flow template ID:
```env
SMS_PROVIDER=msg91
MSG91_AUTH_KEY=<auth key>
MSG91_TEMPLATE_ID=<flow template id>
```
**Twilio** (`SMS_PROVIDER=twilio`): Account SID + Auth Token from the Twilio console and a sender; Indian delivery still requires DLT registration through Twilio support.
```env
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=AC…
TWILIO_AUTH_TOKEN=…
TWILIO_FROM_NUMBER=+1…
```
Users opt in under **Settings → Alert channels → SMS** and must have a mobile number on their profile.

---

## 13. Government SSO (OpenID Connect)

The "Sign in with Government SSO" button appears only when `SSO_ENABLED=true` and an issuer + client are configured. The integration is standard **OIDC Authorization Code + PKCE**, with ID-token signature verification against the provider's JWKS.

**NIC Parichay / MeriPehchaan (government single sign-on):** onboarding is done through NIC — your department's nodal officer applies for integration, registers the application, and receives client credentials. Ask NIC for the OIDC discovery URL (`…/.well-known/openid-configuration`), client ID and secret, and register the redirect URI below. If the provider you are given is not OIDC-compliant, deploy Keycloak as an identity broker in front of it and point Lumen at Keycloak.

**Any OIDC IdP** (Keycloak, Azure AD / Entra ID, Okta):
1. Register a *confidential* web client.
2. Redirect URI: `https://<your-web-domain>/api/auth/sso/callback`.
3. Scopes: `openid profile email`; enable PKCE (S256).
4. Configure:
```env
SSO_ENABLED=true
SSO_PROVIDER_NAME=Government SSO
SSO_ISSUER_URL=https://idp.example.gov.in/realms/coalminegov   # must serve /.well-known/openid-configuration
SSO_CLIENT_ID=coalminegov-web
SSO_CLIENT_SECRET=<secret>
SSO_REDIRECT_URI=https://<your-web-domain>/api/auth/sso/callback
SSO_AUTO_PROVISION=false          # true = create accounts on first login (still need admin scoping)
SSO_ALLOWED_EMAIL_DOMAINS=nic.in,coalindia.in
```
Users are matched to existing accounts by verified e-mail (then by the stable `sub`). With auto-provisioning off, an administrator must create the user first.

**Local test:** `docker compose --profile sso up -d keycloak`, then set
`SSO_ENABLED=true`, `SSO_ISSUER_URL=http://keycloak:8080/realms/coalminegov`, `SSO_CLIENT_ID=coalminegov-web`, `SSO_CLIENT_SECRET=dev-only-keycloak-client-secret`, restart `api`, and sign in as `dgms.regulator` / `Regulator@SSO2026` (matches the seeded regulator by e-mail).

---

## 14. Web push (PWA notifications)

`generate-secrets` prints a VAPID key pair. Set:
```env
VAPID_PUBLIC_KEY=<printed>
VAPID_PRIVATE_KEY=<printed>
VAPID_SUBJECT=mailto:admin@your-domain.gov.in
```
Users enable push per device in **Settings → Push notifications** (HTTPS required outside localhost). Changing the key pair invalidates existing subscriptions.

---

## 15. Maps (GIS tiles)

The default `https://tile.openstreetmap.org` is fine for development but its [usage policy](https://operations.osmfoundation.org/policies/tiles/) forbids heavy production use. For production pick one and set the URL template (`{z}/{x}/{y}` placeholders) and attribution:
* **MapTiler**: create a key at https://cloud.maptiler.com → `https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=<KEY>`
* **Self-hosted tiles** (OpenMapTiles/TileServer GL) — best for air-gapped or government networks.
* **ISRO Bhuvan / MapmyIndia**: obtain a licence/key from the provider and use their XYZ tile endpoint.
```env
NEXT_PUBLIC_MAP_TILE_URL=https://api.maptiler.com/maps/streets-v2/{z}/{x}/{y}.png?key=<KEY>
NEXT_PUBLIC_MAP_ATTRIBUTION=&copy; MapTiler &copy; OpenStreetMap contributors
```
(These are read at runtime by `/api/config`, so no rebuild is needed.) The tile host must be allowed by the CSP `img-src` in `next.config.ts` (HTTPS hosts already are).

The mobile greeting card shows current weather from **Open-Meteo** (no key). Open-Meteo's free tier is for non-commercial use; for production either obtain an Open-Meteo API plan or remove the card.

---

## 16. Observability

* `GRAFANA_ADMIN_PASSWORD` — Grafana admin. Dashboards *Lumen — Platform Health* and *Governance Signals* are provisioned from `infra/grafana`.
* Prometheus scrapes the API (`/metrics`), worker (:9464), consumers (:9465), Temporal, Postgres/Redis/Kafka exporters; alert rules in `infra/prometheus/alerts.yml` (wire them to Alertmanager → e-mail/SMS/pager).
* **Do not expose `/metrics`, Prometheus, Grafana, Temporal UI, Kafka, Redis, Postgres, Qdrant or MinIO to the internet.** In compose all ports bind to `127.0.0.1`; in production keep them on the private network and block `/metrics` at the reverse proxy.

---

## 17. Providing secrets securely in production

**Docker Compose / Swarm** — use `docker secret` or an env file readable only by root (`chmod 600 /etc/coalminegov/.env`), referenced with `--env-file`.

**Kubernetes** — create one Secret per concern and mount as env:
```bash
kubectl create secret generic cmg-app \
  --from-literal=JWT_SECRET_KEY=… --from-literal=PII_ENCRYPTION_KEY=… \
  --from-literal=DATABASE_URL=… --from-literal=REDIS_URL=… --from-literal=LLM_API_KEY=…
```
Better: sync from Vault / AWS Secrets Manager / Azure Key Vault with the External Secrets Operator, enable etcd encryption at rest, and restrict Secret access via RBAC.

**Principles:** separate secrets per environment; least-privilege credentials for every service; rotate on staff changes; audit secret access; never pass secrets as command-line arguments or log them (the app wraps secrets in `SecretStr` and never logs them).

---

## 18. Production deployment checklist

1. `ENVIRONMENT=production`, `DEBUG=false`, `LOG_JSON=true`.
2. HTTPS everywhere: TLS terminates at a reverse proxy/load balancer in front of the web app (and API if exposed). Set `PUBLIC_WEB_URL`, `CORS_ORIGINS=https://…`, `COOKIE_SECURE=true`, `SSO_REDIRECT_URI` to the HTTPS URL.
3. Reverse proxy must forward `X-Forwarded-For`; set `TRUSTED_PROXY_COUNT` to the number of proxies in front of the API (web BFF counts as one). Allow long-lived responses for Server-Sent Events (`/api/proxy/notifications/stream`, `/api/proxy/ai/chat`), e.g. nginx `proxy_buffering off; proxy_read_timeout 1h;`.
4. Managed/HA Postgres with backups; Redis with persistence; Kafka with replication factor 3; Temporal Cloud or HA cluster; Qdrant with snapshots.
5. Run migrations as a one-off job before rolling the app tier: `python -m app.cli migrate`.
6. Scale horizontally: `api` (stateless), `worker` (add replicas on the same task queue), `consumers` (run subsets per container, e.g. `python -m app.consumers.runner audit notifications`).
7. Configure alert routing for `infra/prometheus/alerts.yml`.
8. Security review: WAF/rate limits at the edge, VAPT (CERT-In empanelled auditor for government deployment), GIGW compliance for the public UI.
9. Verify the audit chain regularly: `python -m app.cli verify-audit` (exit code 2 = tampering detected).

---

## 19. Verification commands

```bash
docker compose ps                                     # all services healthy
curl -s localhost:8000/health/ready | python -m json.tool   # postgres/redis/storage/temporal/qdrant checks
docker compose exec api python -m app.cli verify-audit
docker compose logs -f worker consumers               # workflows + event consumers
cd backend && pytest                                  # unit + workflow tests (integration: set TEST_DATABASE_URL)
```

---

## 20. What I need from you (checklist)

- [ ] Target environment and domain name (e.g. `coalminegov.<dept>.gov.in`) + TLS certificate source
- [ ] vLLM endpoints + API key (or a GPU host to run them), and the model names you want to serve
- [ ] Hugging Face read token (only if using gated models)
- [ ] Production PostgreSQL, Redis, Kafka and Qdrant endpoints + credentials — or approval to self-host them
- [ ] Temporal: Temporal Cloud namespace (+ mTLS certs or API key) or self-hosted cluster address
- [ ] Object storage: bucket name, region/endpoint and scoped access keys (or IAM role)
- [ ] SMTP relay credentials and the sender address/domain (with SPF/DKIM set up)
- [ ] SMS: provider choice, DLT entity/header/template IDs, provider auth key
- [ ] Government SSO: issuer/discovery URL, client ID/secret from NIC or your IdP (register the callback URL above)
- [ ] Map tile provider key (MapTiler/Bhuvan/MapmyIndia) or approval to self-host tiles
- [ ] First administrator's e-mail address
- [ ] Data-retention periods for photos/documents/reports (for bucket lifecycle rules)
