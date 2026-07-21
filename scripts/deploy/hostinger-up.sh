#!/usr/bin/env bash
# Bring up BuildMyVersion on a Hostinger VPS (OpenRouter, no Ollama).
# Usage (from repo root):
#   cp .env.prod.example .env   # once
#   # edit .env
#   bash scripts/deploy/hostinger-up.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.prod.yml)

if [[ ! -f .env ]]; then
  echo "Missing .env — copy the template first:"
  echo "  cp .env.prod.example .env"
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

need() {
  local name="$1"
  local val="${!name:-}"
  if [[ -z "$val" || "$val" == CHANGE_ME* || "$val" == *YOUR_DOMAIN* || "$val" == change_this* ]]; then
    echo "Set a real value for $name in .env"
    exit 1
  fi
}

need DOMAIN
need ACME_EMAIL
need ADMIN_PASSWORD
need OPENROUTER_API_KEY

if [[ "${AI_PROVIDER:-openrouter}" != "openrouter" ]]; then
  echo "Warning: AI_PROVIDER=${AI_PROVIDER}. Hostinger guide expects openrouter."
fi

echo "==> Building and starting (Traefik + app, OpenRouter)..."
"${COMPOSE[@]}" up -d --build

echo "==> Waiting for health..."
for i in $(seq 1 60); do
  if curl -fsS "https://${DOMAIN}/api/health" >/dev/null 2>&1 \
    || curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    break
  fi
  # Hit via docker network if TLS not ready yet
  if docker exec bmv-app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" >/dev/null 2>&1; then
    echo "App healthy inside container (TLS may still be provisioning)."
    break
  fi
  sleep 5
  if [[ "$i" -eq 60 ]]; then
    echo "Timed out waiting for health. Check:"
    echo "  ${COMPOSE[*]} ps"
    echo "  ${COMPOSE[*]} logs --tail=80 app"
    exit 1
  fi
done

echo "==> Status"
"${COMPOSE[@]}" ps
echo
echo "Open:  https://${DOMAIN}"
echo "Admin: https://${DOMAIN}/admin"
echo "AI:    curl -sS https://${DOMAIN}/api/ai/status"
echo "Done."
