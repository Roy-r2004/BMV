#!/bin/bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/app/data}"
export DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/buildmyversion.db}"
export UPLOAD_DIR="${UPLOAD_DIR:-/app/data/uploads}"
export STATIC_DIR="${STATIC_DIR:-/app/static}"
export OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0:11434}"

mkdir -p "$DATA_DIR" "$UPLOAD_DIR"

echo "Starting Ollama..."
ollama serve &
OLLAMA_PID=$!

cleanup() {
  echo "Shutting down..."
  kill "$OLLAMA_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Waiting for Ollama..."
for i in $(seq 1 60); do
  if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    echo "Ollama is ready."
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "Warning: Ollama did not become ready in time. AI features may fail until it starts."
  fi
  sleep 2
done

pull_if_missing() {
  local model="$1"
  if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$model"; then
    echo "Model already present: $model"
  else
    echo "Pulling model: $model (this can take a while on first run)..."
    ollama pull "$model" || echo "Warning: failed to pull $model"
  fi
}

if [ "${PULL_MODELS:-true}" = "true" ]; then
  pull_if_missing "${TEXT_MODEL:-llama3.1:8b}"
  pull_if_missing "${VISION_MODEL:-llama3.2-vision}"
  pull_if_missing "${CODER_MODEL:-qwen2.5-coder:7b}"
fi

echo "Starting BuildMyVersion API on port ${PORT:-8000}..."
cd /app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
