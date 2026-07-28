# Environment variables — which file feeds what

One rule: **real values are never committed.** `.gitignore` denies `.env` and
`.env.*` at any depth and re-allows only `*.example` templates.

## File map

| File | Tracked | Consumer | Contains |
|---|---|---|---|
| `backend/.env` | no | `docker-compose.yml` → `api` (via `env_file`), and local `uvicorn` | **Local source of truth** — API keys, models, AppSpec, preview flags |
| `backend/.env.example` | yes | template | Canonical reference for every app var (81 keys) |
| `frontend/.env` | no | `docker-compose.yml` → `web` (via `env_file`), and local `vite` | `VITE_*` only — these ship to the browser, so never put a secret here |
| `frontend/.env.example` | yes | template | — |
| `.env` (root) | no | `docker-compose.yml` interpolation **only** | Optional. Just `POSTGRES_*` + `SEED_DEMO`, all of which already have compose defaults |
| `.env.example` (root) | yes | template | — |
| `.env.prod` | no | your local paste source for the Coolify UI | Real production values |
| `.env.prod.example` | yes | template | Production placeholders, complete for both prod paths |

Deleted: `.env.staging.example` — staging is retired, along with the v2 staging
stack it existed for.

## Local development

```bash
cp backend/.env.example backend/.env     # then set OPENROUTER_API_KEY + ADMIN_PASSWORD
cp frontend/.env.example frontend/.env
docker compose up --build
```

Frontend `http://localhost:5173` · API `http://localhost:8001`.

A root `.env` is **not** required — Compose loads `backend/.env` via `env_file` and
defaults every `POSTGRES_*` value.

After editing `backend/.env`, recreate the container:

```bash
docker compose up -d api      # applies env_file changes
docker compose restart api    # does NOT — reuses the old container env
```

`docker compose config` will show the new value even when the running container
still has the old one, so verify with `docker compose exec api env | grep KEY`.

Duplicate keys in an env file resolve **last-wins**, which is a convenient way to
append an override block without editing the lines above it.

### Which models the preview generator needs

`PREVIEW_APP_MODEL` drives codegen (architect, per-file generation, slot fill).
It is the single setting most likely to change output quality, and a slow model
does more than cost time — it degrades the result:

| Model | Observed on the Jeanne Kassab gallery request |
|---|---|
| `google/gemini-2.5-flash` | Request 22's reference run — 5 codegen calls, avg 25.6s, max 55.5s, all successful |
| `deepseek/deepseek-v4-pro` | Truncated slot-fill output on one admin page, fell back to scaffold on a public page, and held one codegen worker open past 10 minutes |

When a slot-fill call fails or is truncated, codegen **keeps the scaffold** rather
than failing the build. So a slow model does not error — it silently ships
lower-fidelity pages. If output quality drops, check `PREVIEW_APP_MODEL` before
anything else, and confirm what actually ran:

```sql
SELECT model, purpose, count(*), round(avg(latency_ms)/1000.0, 1) AS avg_s
FROM ai_usage_events WHERE request_id = :id GROUP BY model, purpose;
```

Note that the nominal 120s provider timeout does **not** bound total call
duration: it is a `requests` read timeout, so it only trips on inactivity
between bytes. A provider that trickles output can hold a worker open
indefinitely.

## Production

Two supported paths. Both read from the same template.

**Path A — Hostinger VPS** (`docker-compose.prod.yml` + Traefik):

```bash
cp .env.prod.example .env    # on the server
nano .env                    # fill every CHANGE_ME
bash scripts/deploy/hostinger-up.sh
```

**Path B — Coolify** (`docker-compose.coolify.yml`, or `Dockerfile.app` via the UI):
paste the keys into the Coolify environment editor. Keep `.env.prod` locally as the
paste source. Mount Persistent Storage at `/app/data` so SQLite and preview builds
survive redeploys.

## Compose forwards the whole env file

Neither prod compose used to use `env_file`; each forwarded an explicit allowlist,
so a key set in `.env` that was absent from that list was silently dropped and the
app fell back to its `backend/app/core/config.py` default. Both now declare:

```yaml
env_file:
  - path: .env
    required: false
```

`environment:` still takes precedence, so Docker-specific paths, `DATABASE_URL`,
and the `:?` required-var assertions are unaffected — but nothing drifts silently
any more. Verify what a container actually received with:

```bash
docker compose exec api env | grep KEY
```

## Adding a new variable

1. Add it to `backend/app/core/config.py` with a safe default.
2. Add it to `backend/.env.example` with a comment.
3. If production needs it, add it to `.env.prod.example`. It reaches the container
   automatically via `env_file` — you only need an `environment:` entry when the
   value must be *fixed* by the deployment (a container path, `DATABASE_URL`) or
   asserted as required with `:?`.
