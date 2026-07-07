#!/bin/bash
set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-ollama:11434}"
export OLLAMA_HOST

TEXT_MODEL="${TEXT_MODEL:-llama3.1:8b}"
VISION_MODEL="${VISION_MODEL:-llama3.2-vision}"
CODER_MODEL="${CODER_MODEL:-qwen2.5-coder:7b}"

echo "Waiting for Ollama at ${OLLAMA_HOST}..."
for i in $(seq 1 60); do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

pull_if_missing() {
  local model="$1"
  if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "$model"; then
    echo "Model already present: $model"
  else
    echo "Pulling model: $model ..."
    ollama pull "$model"
  fi
}

if [ "${PULL_MODELS:-true}" = "true" ]; then
  pull_if_missing "$TEXT_MODEL"
  pull_if_missing "$VISION_MODEL"
  pull_if_missing "$CODER_MODEL"
  echo "All models ready."
else
  echo "PULL_MODELS=false — skipping model pull."
fi
