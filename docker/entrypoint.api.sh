#!/bin/bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/app/data}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/buildmyversion.db}"
export UPLOAD_DIR="${UPLOAD_DIR:-/app/data/uploads}"
export PREVIEW_TEMPLATE_DIR="${PREVIEW_TEMPLATE_DIR:-/app/backend/preview-template}"
export PREVIEW_APPS_DIR="${PREVIEW_APPS_DIR:-/app/data/preview-apps}"
export INTERNAL_BASE_URL="${INTERNAL_BASE_URL:-http://127.0.0.1:${PORT:-8000}}"
export PATH="/opt/node/bin:${PATH}"

mkdir -p "$DATA_DIR" "$UPLOAD_DIR" "$PREVIEW_APPS_DIR"

if [ "${AI_PROVIDER:-}" = "ollama" ]; then
  OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
  echo "Waiting for Ollama at ${OLLAMA_URL}..."
  for i in $(seq 1 30); do
    if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
      echo "Ollama is ready."
      break
    fi
    sleep 2
  done
fi

cd /app/backend
if [ ! -f "${PREVIEW_TEMPLATE_DIR}/node_modules/typescript/package.json" ]; then
  echo "preview-template node_modules missing typescript; running npm ci..."
  npm ci --prefix "${PREVIEW_TEMPLATE_DIR}"
fi

echo "Starting BuildMyVersion API on port ${PORT:-8000}..."

UVICORN_ARGS=(--host 0.0.0.0 --port "${PORT:-8000}")
if [ "${UVICORN_RELOAD:-false}" = "true" ] || [ "${UVICORN_RELOAD:-false}" = "1" ]; then
  UVICORN_ARGS+=(
    --reload
    --reload-dir /app/backend/app
    --reload-dir /app/backend/preview-template
  )
  # Bind mounts on Docker Desktop (macOS/Windows) often miss inotify events.
  export WATCHFILES_FORCE_POLLING="${WATCHFILES_FORCE_POLLING:-true}"
fi

exec python -m uvicorn app.main:app "${UVICORN_ARGS[@]}"
