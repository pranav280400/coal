#!/usr/bin/env bash
# Creates .env from .env.example and fills in every secret the stack needs.
#
#   ./scripts/bootstrap-env.sh
#
# Safe to re-run: values that are already set are never overwritten — only blank keys get a
# freshly generated value. Nothing leaves your machine; the secrets are generated locally
# inside the backend image (python -m app.cli generate-secrets).
#
# This deliberately uses plain `docker build` / `docker run` rather than `docker compose`,
# because compose refuses to run at all until .env is filled in — which is what this
# script is for.

set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=".env"
IMAGE="coalminegov/backend:bootstrap"

info() { printf '  %s\n' "$1"; }
step() { printf '\n==> %s\n' "$1"; }

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is not running. Start Docker Desktop, wait for the whale icon to" >&2
  echo "       stop animating, then run this script again." >&2
  exit 1
fi

step "Preparing $ENV_FILE"
if [ ! -f "$ENV_FILE" ]; then
  cp .env.example "$ENV_FILE"
  info "created $ENV_FILE from .env.example"
else
  cp "$ENV_FILE" "$ENV_FILE.backup"
  info "$ENV_FILE already exists - backed it up to $ENV_FILE.backup"
fi

step "Building the backend image (first run takes a few minutes)"
docker build -t "$IMAGE" ./backend

gen() { docker run --rm --entrypoint python "$IMAGE" "$@"; }

step "Generating secrets"
SECRETS="$(gen -m app.cli generate-secrets)"

# Replace `KEY=` (blank, optionally followed by a comment) with `KEY=<value>`.
# Keys that already carry a value are left untouched. Generated values are url-safe
# base64, so `|` is always a safe sed delimiter.
fill() {
  local key="$1" value="$2"
  if grep -qE "^${key}=[[:space:]]*(#.*)?$" "$ENV_FILE"; then
    sed -E "s|^${key}=[[:space:]]*(#.*)?$|${key}=${value}|" "$ENV_FILE" > "$ENV_FILE.tmp"
    mv "$ENV_FILE.tmp" "$ENV_FILE"
    info "set $key"
  else
    info "kept existing $key"
  fi
}

while IFS= read -r line; do
  case "$line" in
    \#*|"") continue ;;
    *=*) fill "${line%%=*}" "${line#*=}" ;;
  esac
done <<< "$SECRETS"

step "First administrator account"
if grep -qE '^BOOTSTRAP_ADMIN_EMAIL=[[:space:]]*(#.*)?$' "$ENV_FILE"; then
  read -r -p "  Admin e-mail address: " ADMIN_EMAIL
  fill BOOTSTRAP_ADMIN_EMAIL "$ADMIN_EMAIL"
else
  info "kept existing BOOTSTRAP_ADMIN_EMAIL"
fi

if grep -qE '^BOOTSTRAP_ADMIN_PASSWORD=[[:space:]]*(#.*)?$' "$ENV_FILE"; then
  read -r -s -p "  Admin password (10+ chars, upper+lower+digit+symbol; press Enter to generate one): " ADMIN_PW; echo
  if [ -z "$ADMIN_PW" ]; then
    ADMIN_PW="$(gen -c 'import secrets,string; a=string.ascii_letters+string.digits; print("Cmg#"+"".join(secrets.choice(a) for _ in range(16)))')"
    info "generated one - it is saved in $ENV_FILE as BOOTSTRAP_ADMIN_PASSWORD"
  fi
  fill BOOTSTRAP_ADMIN_PASSWORD "$ADMIN_PW"
else
  info "kept existing BOOTSTRAP_ADMIN_PASSWORD"
fi

chmod 600 "$ENV_FILE" 2>/dev/null || true

cat <<'EOF'

==> Done. .env is ready.

Next:
    docker compose up -d --build
    docker compose ps                                      # wait for api + web = healthy
    docker compose exec api python -m app.cli seed-demo     # optional demo data

Then open http://localhost:3000 and sign in with the admin e-mail + password above.

AI features (assistant, semantic search, AI severity suggestions) stay off until you point
VLLM_CHAT_API_BASE / VLLM_EMBED_API_BASE at a real inference server - see
docs/CREDENTIALS_AND_SETUP.md section 6. Everything else works without them.
EOF
