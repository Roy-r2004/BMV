#!/bin/bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/app/data}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/buildmyversion.db}"
export UPLOAD_DIR="${UPLOAD_DIR:-/app/data/uploads}"
export STATIC_DIR="${STATIC_DIR:-/app/static}"
export OLLAMA_URL="${OLLAMA_URL:-http://ollama:11434}"

mkdir -p "$DATA_DIR" "$UPLOAD_DIR"

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

echo "Starting BuildMyVersion API on port ${PORT:-8000}..."
cd /app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
