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

echo "[boot] AI_PROVIDER=${AI_PROVIDER:-unset}"
echo "[boot] PREVIEW_TEMPLATE_DIR=${PREVIEW_TEMPLATE_DIR} exists=$(test -d "$PREVIEW_TEMPLATE_DIR" && echo yes || echo no)"
echo "[boot] node=$(node -v 2>/dev/null || echo missing) npm=$(npm -v 2>/dev/null || echo missing)"
echo "[boot] INTERNAL_BASE_URL=${INTERNAL_BASE_URL}"

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

echo "Starting BuildMyVersion API on port ${PORT:-8000}..."
cd /app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
