# Staging Deployment — Commercial Workflow Readiness

Dedicated staging environment for Preview Generator v2 with Expanded Preview commercial controls.

## What this is

- Separate Docker Compose stack: `docker-compose.staging.yml`
- Separate Postgres volume and API data volume
- Separate preview candidate / validation / upload paths under `/app/data`
- Fail-closed Phase 7 hard gates (percent = 0, no live canary/providers, no promote, no auto-rollback)
- `V2_TIER2_GENERATION_ENABLED=true` means **admin-approved capability only** — Tier 2 does **not** auto-start after Tier 1 visual acceptance

## Prerequisites

1. Docker + Docker Compose
2. Copy env example and set unique staging secrets:

```bash
cp .env.staging.example .env.staging
# edit ADMIN_*, POSTGRES_PASSWORD, optional staging-only OPENROUTER_API_KEY
# never reuse production credentials or production DATABASE_URL
```

## Deploy

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
```

API publishes on host port `8002` by default; web on `5174` (override with `STAGING_API_PORT` / `STAGING_WEB_PORT`).

Migrations run at API process start and **abort startup** if required schema versions (through `phase7f.2` and `commercial.1`) are missing.

## Verify

```bash
chmod +x scripts/verify-staging.sh
./scripts/verify-staging.sh http://127.0.0.1:8002 http://127.0.0.1:5174
```

Checks:

- `/api/health/live`
- `/api/health/ready` (must include `phase7f.2`)
- hard-gate flags inside the API container
- frontend reachability
- readiness payload must not contain credentials

## Health endpoints

| Route | Meaning |
|---|---|
| `GET /api/health/live` | Process is up |
| `GET /api/health/ready` | DB reachable + required schema versions present |
| `GET /api/health` | Legacy liveness alias |

## Expanded Preview smoke (manual)

1. Submit a business on the staging frontend (`/submit`).
2. Wait for Tier 1 preview on `/result/:id`.
3. Use **Request Expanded Preview** (does not start Tier 2).
4. Open admin → **Expanded** queue → approve → confirm **Start Tier 2**.
5. Review → accept → confirm **Publish**.
6. Customer sees published Expanded Preview link.

## Rollback

Redeploy previous application git SHA without deleting migration history:

```bash
git checkout <previous-sha>
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
```

Do **not** run destructive Phase 7 / commercial downgrades when history rows exist.

## Hard gates (must remain)

```text
APP_ENV=staging
V2_PHASE7_ROLLOUT_PERCENT=0
V2_PHASE7_PERCENT_SERVE_ENABLED=false
V2_PHASE7_LIVE_CANARY_ENABLED=false
V2_PHASE7_LIVE_CANARY_PROVIDERS_ENABLED=false
V2_PHASE7_AUTO_ROLLBACK_ENABLED=false
V2_PHASE7_PROMOTE_ENABLED=false
V2_PHASE7_SHADOW_LIVE_PROVIDERS_ENABLED=false
V2_PHASE7_CANARY_SIMULATION_ENABLED=false
V2_TIER2_GENERATION_ENABLED=true
V2_TIER3_GENERATION_ENABLED=false
```
