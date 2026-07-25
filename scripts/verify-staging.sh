#!/usr/bin/env bash
# Verify a staging deployment without printing secrets.
# Usage:
#   ./scripts/verify-staging.sh https://staging-api.example.com [https://staging-web.example.com]
set -euo pipefail

API_BASE="${1:-http://127.0.0.1:8002}"
WEB_BASE="${2:-}"

redacted_ok() {
  echo "$1"
}

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

echo "Checking API liveness at ${API_BASE}/api/health/live"
live="$(curl -fsS "${API_BASE}/api/health/live")"
echo "${live}" | grep -q '"live"[[:space:]]*:[[:space:]]*true' || fail "liveness check failed"

echo "Checking API readiness at ${API_BASE}/api/health/ready"
ready_body="$(curl -fsS "${API_BASE}/api/health/ready" || true)"
echo "${ready_body}" | grep -q '"ready"[[:space:]]*:[[:space:]]*true' || fail "readiness check failed"
echo "${ready_body}" | grep -q 'phase7f.2' || fail "phase7f.2 schema version missing from readiness payload"
echo "${ready_body}" | grep -qiE 'password|postgres://[^:]+:[^@]+@' && fail "credentials leaked in readiness payload"
redacted_ok "readiness OK (schema versions present; no credential leak detected)"

echo "Checking fail-closed Phase 7 hard gates via Python in API container (if compose available)"
if docker compose -f docker-compose.staging.yml ps api >/dev/null 2>&1; then
  docker compose -f docker-compose.staging.yml exec -T api python - <<'PY'
from app.core.config import Settings
import os
# Prefer process env already injected into the container.
s = Settings()
assert s.V2_PHASE7_ROLLOUT_PERCENT == 0, s.V2_PHASE7_ROLLOUT_PERCENT
assert s.V2_PHASE7_PERCENT_SERVE_ENABLED is False
assert s.V2_PHASE7_LIVE_CANARY_ENABLED is False
assert s.V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED is False
assert s.V2_PHASE7_AUTO_ROLLBACK_ENABLED is False
assert s.V2_PHASE7_PROMOTE_ENABLED is False
assert s.V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED is False
assert s.V2_PHASE7_CANARY_SIMULATION_ENABLED is False
assert s.V2_TIER2_GENERATION_ENABLED is True
assert s.V2_TIER3_GENERATION_ENABLED is False
print("hard_gates_ok")
PY
else
  echo "WARN: docker compose staging api not running locally; skipped in-container flag check"
fi

if [[ -n "${WEB_BASE}" ]]; then
  echo "Checking frontend at ${WEB_BASE}"
  code="$(curl -sS -o /dev/null -w '%{http_code}' "${WEB_BASE}/")"
  [[ "${code}" == "200" || "${code}" == "301" || "${code}" == "302" ]] || fail "frontend not reachable (HTTP ${code})"
  redacted_ok "frontend reachable"
fi

echo "Staging verification passed."
