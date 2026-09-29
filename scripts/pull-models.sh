#!/usr/bin/env bash
# Download the local AI models into the `ollamadata` volume (one-off, ~1.5 GB).
#
#   docker compose --profile cpu-ai up -d ollama
#   ./scripts/pull-models.sh
#
# The model names must match infra/litellm/config.yaml. The embedding model must emit
# vectors of EMBEDDING_DIM (default 1024) — bge-m3 does.

set -euo pipefail
cd "$(dirname "$0")/.."

CHAT_MODEL="${OLLAMA_CHAT_MODEL:-qwen2.5:3b-instruct}"
EMBED_MODEL="${OLLAMA_EMBED_MODEL:-bge-m3}"

if ! docker compose --profile cpu-ai ps ollama --format '{{.Status}}' 2>/dev/null | grep -q 'Up'; then
  echo "Starting the ollama service first..."
  docker compose --profile cpu-ai up -d ollama
  echo "Waiting for it to accept connections..."
  for _ in $(seq 1 30); do
    docker compose --profile cpu-ai exec -T ollama ollama list >/dev/null 2>&1 && break
    sleep 5
  done
fi

for m in "$EMBED_MODEL" "$CHAT_MODEL"; do
  echo "==> pulling $m"
  docker compose --profile cpu-ai exec -T ollama ollama pull "$m"
done

echo
docker compose --profile cpu-ai exec -T ollama ollama list
cat <<'EOF'

Models are cached in the `coalminegov_ollamadata` volume, so this is a one-time download.

Next:
    docker compose restart litellm api worker consumers
    docker compose exec api python -m app.cli reindex-knowledge   # build the RAG index

Then open http://localhost:3000/assistant and ask a question.
EOF
