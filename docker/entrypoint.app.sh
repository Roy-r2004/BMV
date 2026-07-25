#!/bin/bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/app/data}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/buildmyversion.db}"
export UPLOAD_DIR="${UPLOAD_DIR:-/app/data/uploads}"
export STATIC_DIR="${STATIC_DIR:-/app/static}"
export PREVIEW_TEMPLATE_DIR="${PREVIEW_TEMPLATE_DIR:-/app/backend/preview-template}"
export PREVIEW_APPS_DIR="${PREVIEW_APPS_DIR:-/app/data/preview-apps}"
export OLLAMA_URL="${OLLAMA_URL:-http://ollama:11434}"
AI_PROVIDER="${AI_PROVIDER:-openrouter}"

mkdir -p "$DATA_DIR" "$UPLOAD_DIR" "$PREVIEW_APPS_DIR"

# Builds (SQLite + preview-apps) must live on a Coolify/Docker persistent volume
# mounted at /app/data. Without that, every redeploy starts empty.
export SEED_DEMO="${SEED_DEMO:-false}"
echo "Data dir: ${DATA_DIR} (db=$( [ -f "${DATA_DIR}/buildmyversion.db" ] && echo present || echo missing )) SEED_DEMO=${SEED_DEMO}"
if [ ! -f "${DATA_DIR}/buildmyversion.db" ]; then
  echo "NOTE: No SQLite DB yet under ${DATA_DIR}. On Coolify, attach Persistent Storage to /app/data so builds survive redeploys."
fi

if [ "$AI_PROVIDER" = "ollama" ]; then
  echo "Waiting for Ollama at ${OLLAMA_URL}..."
  for i in $(seq 1 90); do
    if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
      echo "Ollama is ready."
      break
    fi
    if [ "$i" -eq 90 ]; then
      echo "Warning: Ollama did not become ready in time. AI features may fail until it starts."
    fi
    sleep 2
  done
else
  echo "AI_PROVIDER=${AI_PROVIDER} — skipping Ollama wait."
fi

cd /app/backend
if [ ! -f "${PREVIEW_TEMPLATE_DIR}/node_modules/typescript/package.json" ]; then
  echo "preview-template node_modules missing typescript; running npm ci..."
  npm ci --prefix "${PREVIEW_TEMPLATE_DIR}"
fi

echo "Starting BuildMyVersion API on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
