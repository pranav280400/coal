# Getting Started — a step-by-step guide for first-time setup

This guide assumes **no prior Docker or backend experience**. Follow it top to bottom and
you will have the whole platform running on your own machine.

If you already know Docker and just want the reference list of every credential the system
can take, read [CREDENTIALS_AND_SETUP.md](CREDENTIALS_AND_SETUP.md) instead. This page is
the friendly version.

---

## Part 0 — What you actually need before you start

Here is the honest answer to *"what do I have to provide?"*

### You need NOTHING from anyone else to run the system locally.

Really. Step 1 below generates every password and key automatically, on your machine.
Postgres, Redis, Kafka, Qdrant, Temporal, MinIO, Prometheus and Grafana all run inside
Docker with locally generated credentials. You can log in, click through every dashboard,
file inspections, raise violations and watch workflows escalate — all offline.

### Two things you must type in yourself (30 seconds)

| What | Why | Where you get it |
|---|---|---|
| An e-mail address for the first administrator | The system creates your first login with it. It is never e-mailed anywhere unless you switch on SMTP later. | Any address you own — `you@example.com` is fine for local use |
| A password for that administrator | Your login password | Invent one: at least 10 characters with an upper-case letter, a lower-case letter, a digit and a symbol. Or press Enter and the script generates one for you. |

### One thing you need only for the AI features

| What | Why | How to get it |
|---|---|---|
| A vLLM (or any OpenAI-compatible) server URL + its API key | Powers the AI assistant, semantic search, AI-suggested violation severity and AI report summaries | See [Part 5](#part-5--turning-on-the-ai-features) — you likely already have one; if not, the rest of the platform works without it |

**Everything else** — SMS gateways, government SSO, real e-mail, map tile keys, TLS
certificates, cloud databases — is **only for production**. Skip all of it for now.
[Part 6](#part-6--what-you-will-need-later-for-a-real-deployment) lists them with
instructions for when you get there.

---

## Part 1 — Install Docker

1. Download **Docker Desktop** from <https://www.docker.com/products/docker-desktop/> and
   install it (on Windows, accept the WSL 2 prompt if it appears).
2. Start Docker Desktop. Wait until the whale icon in the system tray **stops animating** —
   that means the engine is ready. This can take a minute or two on first launch.
3. Give Docker enough memory. The full stack is 17 containers.
   * **Windows/Mac:** Docker Desktop → *Settings* → *Resources* → set **Memory to 8 GB or
     more** (12 GB if you have it) → *Apply & Restart*.
   * On Windows with WSL 2 the memory slider may be missing; see
     [Troubleshooting](#not-enough-memory-on-windows-wsl-2) below.
4. Check it works. Open a terminal (PowerShell on Windows, Terminal on Mac/Linux) and run:

```bash
docker --version
```

You should see something like `Docker version 29.x`. If you get "command not found",
Docker Desktop is not installed or not started.

---

## Part 2 — Create your configuration file

The project reads all its settings from a file called `.env`. It does not exist yet, and it
must contain about a dozen strong random passwords. A script does all of that for you.

Open a terminal **in the project folder** (the one containing `docker-compose.yml`) and run:

**Windows (PowerShell):**
```bash
.\scripts\bootstrap-env.ps1
```

**Mac / Linux:**
```bash
./scripts/bootstrap-env.sh
```

What it does:

1. Copies `.env.example` to `.env`.
2. Builds the backend container image (first time: a few minutes — it downloads Python and
   the OCR engine).
3. Generates every password and encryption key **locally, inside that container**. Nothing
   is sent over the internet.
4. Asks you for the administrator e-mail address and password from Part 0.
5. Writes them all into `.env`.

It is safe to run again — it never overwrites a value you already set, and it backs up any
existing `.env` to `.env.backup` first.

> **Keep `.env` private.** It now holds real passwords. It is already listed in
> `.gitignore`, so git will not commit it. Do not e-mail it or paste it into a chat.

---

## Part 3 — Start everything

```bash
docker compose up -d --build
```

* `up` starts the containers, `-d` runs them in the background, `--build` builds the two
  application images (backend and web) from the source in this repo.
* **The first run takes 10–20 minutes**: it downloads about 4 GB of images and compiles the
  frontend. Later runs take under a minute.

Watch progress:

```bash
docker compose ps
```

Repeat that every 30 seconds or so. You are waiting for `api` and `web` to say
**`healthy`**. Services start in order — Postgres first, then migrations, then the API,
then the web app — so it is normal for several to show `starting` or `created` for a while.

When `docker compose ps` shows `healthy` for `api` and `web`, you are running.

### Add demo data (recommended)

Empty dashboards are hard to judge. This loads 21 realistic Coal India mines with a year of
inspections, violations and corrective actions:

```bash
docker compose exec api python -m app.cli seed-demo
```

---

## Part 4 — Open it

| Address | What it is | How to log in |
|---|---|---|
| <http://localhost:3000> | **The application** — dashboards, inspections, violations, map | Your admin e-mail + password from Part 2 |
| <http://localhost:8000/docs> | API reference (every endpoint, try-it-out buttons) | — |
| <http://localhost:8233> | Temporal UI — watch the escalation workflows run | — |
| <http://localhost:3001> | Grafana — platform health dashboards | user `admin`, password = `GRAFANA_ADMIN_PASSWORD` in your `.env` |
| <http://localhost:9090> | Prometheus — raw metrics | — |
| <http://localhost:9001> | MinIO console — uploaded photos and documents | user/password = `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` in `.env` |

If you ran `seed-demo`, you can also sign in as each role to see the different dashboards.
All demo accounts use the password `CoalMine@2026`:

| Username | Role |
|---|---|
| `ravi.kumar` | Mine official — single site |
| `suresh.patnaik` | Corporate — one subsidiary (MCL) |
| `anita.sharma` | Corporate — Coal India HQ, all subsidiaries |
| `dgms.regulator` | Regulator — read-only, cross-subsidiary |
| `contractor.demo` | Contractor |

---

## Part 5 — Turning on the AI features

Without this section the platform runs completely, but:

* the **AI Assistant** page reports the gateway as unavailable,
* **semantic search** returns nothing,
* **violation severity suggestions** fall back to a transparent rules engine (clearly
  labelled "rules" in the UI),
* **report summaries** are generated without the narrative paragraph.

Risk scoring and anomaly detection are **not** affected — those are local scikit-learn
models and always work.

To switch AI on you need an **OpenAI-compatible inference endpoint**. Three options:

### Option 0 (already set up) - local CPU model, no GPU and no API key

This machine has no NVIDIA GPU, so the stack is configured to run the models on plain CPU
via Ollama. Everything is already downloaded and wired up; to start it:

```bash
docker compose --profile cpu-ai up -d ollama
docker compose exec api python -m app.cli reindex-knowledge
```

Models live in the `coalminegov_ollamadata` Docker volume (a one-time ~3 GB download; use
`./scripts/pull-models.sh` or `.\scripts\pull-models.ps1` on a fresh machine). Nothing
leaves your computer, which matters for the data-residency rules in section 13.

**What to expect on CPU:** answers are accurate and cited, but slow - roughly 30 seconds to
the first word and 60-90 seconds for a full answer. Replies stream, so text appears as it
is generated. Hindi and other Indian languages need a larger model than a laptop CPU can
run usefully; use Option A or B for genuine multilingual work.

To trade accuracy for speed, edit `infra/litellm/config.yaml` and change
`ollama_chat/qwen2.5:3b-instruct` to `ollama_chat/qwen2.5:1.5b-instruct` (about 3x faster,
but it will occasionally invent regulation numbers), then
`docker compose restart litellm`.

### Option A — you already have vLLM running somewhere

This is the common case. Ask whoever runs it for three things:

1. The **chat endpoint URL**, ending in `/v1` — e.g. `http://192.168.1.50:8000/v1`
2. The **embeddings endpoint URL**, also ending in `/v1` (it may be the same server)
3. The **API key** the server was started with (`--api-key`); if it was started without
   one, leave the key blank

Then open `.env` in a text editor and set:

```env
VLLM_CHAT_API_BASE=http://192.168.1.50:8000/v1
VLLM_EMBED_API_BASE=http://192.168.1.50:8001/v1
VLLM_API_KEY=<the key, or leave empty>
```

Two requirements on that server:
* the chat model must be served under the name **`cmg-chat`** (vLLM flag:
  `--served-model-name cmg-chat`);
* the embedding model under **`cmg-embed`**, and it must produce **1024-dimension**
  vectors (`BAAI/bge-m3` does). If yours produces a different size, also set
  `EMBEDDING_DIM=<that size>` **before the first start** — the vector database collection
  is created with that dimension and changing it later means re-indexing.

Apply the change:

```bash
docker compose up -d litellm api worker consumers
```

### Option B — run vLLM on this machine

Only possible with an **NVIDIA GPU with 24 GB or more of VRAM** (L4, A10G, RTX 4090,
A100) and the NVIDIA Container Toolkit installed. Then:

```bash
docker compose --profile gpu up -d
```

The first start downloads about 16 GB of model weights. If the model is gated on Hugging
Face (Llama models are), create a free *Read* token at
<https://huggingface.co/settings/tokens>, accept the licence on the model's page, and put
the token in `.env` as `HF_TOKEN=hf_...`.

### Check it worked

```bash
docker compose exec api python -c "import urllib.request,json,os; print(urllib.request.urlopen('http://localhost:8000/health/ready').read().decode())"
```

Look for `"qdrant": true`. Then open the **AI Assistant** page in the app and ask a
question — answers should come back with citations.

---

## Part 6 — What you will need later, for a real deployment

None of this is needed for local use. Collect it when you are ready to put the system on a
real server with a real domain name.

| # | What to obtain | Who gives it to you | Roughly how long |
|---|---|---|---|
| 1 | **Domain name + TLS certificate** — e.g. `coalminegov.<dept>.gov.in` | Your department's IT/NIC coordinator; or Let's Encrypt (free, automatic) | Days to weeks for a `.gov.in` domain |
| 2 | **A server or cloud account** to host it | Your organisation | — |
| 3 | **Managed PostgreSQL** (or self-host) | AWS RDS / Azure Database / NIC MeghRaj | Hours |
| 4 | **Managed Redis and Kafka** (or self-host) | Same provider — AWS ElastiCache + MSK, Confluent Cloud, Aiven | Hours |
| 5 | **Object storage bucket** for photos and documents | AWS S3 (`ap-south-1`), or your NIC cloud's S3-compatible storage | Hours |
| 6 | **SMTP relay** so the system can send e-mail (password resets, escalation alerts) | NIC e-mail relay via your coordinator, or AWS SES, or SendGrid | Days (domain verification) |
| 7 | **SMS gateway + TRAI DLT registration** — only if you want SMS alerts | MSG91 or Twilio, **plus** DLT registration on a telecom operator's portal. India legally requires DLT for commercial SMS. | 1–2 weeks — start early |
| 8 | **Government SSO (OIDC) client** — only if you want "Sign in with Government SSO" | NIC Parichay / MeriPehchaan, applied for by your department's nodal officer. You need: discovery URL, client ID, client secret. | Weeks |
| 9 | **Map tile provider key** — the default OpenStreetMap tiles are not licensed for heavy production use | MapTiler (free tier, instant), ISRO Bhuvan, or MapmyIndia | Minutes to days |
| 10 | **Security audit (VAPT)** — mandatory for government deployment | A CERT-In empanelled auditor | Weeks |

Exact environment-variable names and provider-by-provider instructions for each of these
are in [CREDENTIALS_AND_SETUP.md](CREDENTIALS_AND_SETUP.md), sections 4–16, and the
production checklist is section 18.

---

## Everyday commands

```bash
docker compose ps                    # what is running, and is it healthy
docker compose logs -f api           # follow the API log (Ctrl-C to stop watching)
docker compose logs -f worker        # follow the workflow engine
docker compose restart api           # restart one service
docker compose stop                  # stop everything, keep the data
docker compose up -d                 # start it again
docker compose down                  # stop and remove containers, keep the data
docker compose down -v               # DANGER: also deletes all data and starts fresh
```

To apply code changes: `docker compose up -d --build`.

---

## Troubleshooting

### `docker compose up` stops immediately with "missing POSTGRES_PASSWORD"

You skipped Part 2, or `.env` is missing. Run the bootstrap script.

### A service keeps restarting

Look at why:

```bash
docker compose logs --tail=50 <service-name>
```

### `api` never becomes healthy

Check the migration job first — the API waits for it:

```bash
docker compose logs migrate
```

### Not enough memory on Windows (WSL 2)

If containers are being killed, or Docker Desktop has no memory slider, create a file at
`C:\Users\<you>\.wslconfig` containing:

```ini
[wsl2]
memory=10GB
processors=4
```

Then run `wsl --shutdown` in PowerShell and restart Docker Desktop.

You can also lower the platform's own appetite by editing `.env`:

```env
API_WORKERS=2
```

and restarting with `docker compose up -d api`.

### Port already in use

A service refuses to start with a message like:

```
ports are not available: exposing port TCP 127.0.0.1:5432 -> ...
bind: An attempt was made to access a socket in a way forbidden by its access permissions
```

Something else on your computer already owns that port. **A PostgreSQL server installed
directly on the machine is by far the most common cause** — it owns 5432.

You do not need to uninstall anything. Every port is settable in `.env`; pick a free one:

```env
POSTGRES_HOST_PORT=5433
```

then `docker compose up -d`. This changes only how *you* reach the service from your own
machine — the containers still talk to each other on their normal ports, so nothing else
has to change.

The full list of adjustable ports is in the `host ports (compose)` section of `.env`:
`POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`, `KAFKA_HOST_PORT`, `QDRANT_HOST_PORT`,
`MINIO_HOST_PORT`, `MINIO_CONSOLE_HOST_PORT`, `TEMPORAL_HOST_PORT`,
`TEMPORAL_UI_HOST_PORT`, `LITELLM_HOST_PORT`, `API_HOST_PORT`, `WEB_HOST_PORT`,
`PROMETHEUS_HOST_PORT`, `GRAFANA_HOST_PORT`, `KEYCLOAK_HOST_PORT`.

On Windows, the same error can also come from Hyper-V having reserved a port range. Check
with `netsh interface ipv4 show excludedportrange protocol=tcp` in PowerShell; if your port
falls inside a reserved range, just pick a different one as above.

To find out what owns a port on Windows:

```bash
Get-NetTCPConnection -LocalPort 5432 | Select-Object OwningProcess
```

### "pull access denied" on an image

Your network blocks a registry, or you are behind a proxy. Configure the proxy in Docker
Desktop → *Settings* → *Resources* → *Proxies*.

### Start completely over

```bash
docker compose down -v
docker compose up -d --build
```

`-v` deletes the database volumes, so all data is lost — including the demo data, which you
can reload with `seed-demo`.

---

## Where to go next

* [CREDENTIALS_AND_SETUP.md](CREDENTIALS_AND_SETUP.md) — every configuration value, and how
  to obtain each credential from each provider
* [../README.md](../README.md) — what the platform does and how the pieces fit together
* [../requirements.md](../requirements.md) — the original architecture and requirements
