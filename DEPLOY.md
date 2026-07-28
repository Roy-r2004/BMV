# Deploy

Both production paths read the same template, [.env.prod.example](.env.prod.example).
Env layout and the compose allowlist caveat: [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

## Path A — Hostinger VPS + OpenRouter

Full guide: [docs/deploy/hostinger-openrouter.md](docs/deploy/hostinger-openrouter.md).

```bash
cp .env.prod.example .env
# fill every CHANGE_ME — at minimum DOMAIN, ACME_EMAIL, ADMIN_PASSWORD, OPENROUTER_API_KEY
bash scripts/deploy/hostinger-up.sh
```

Uses `docker-compose.prod.yml` (Traefik + Let's Encrypt).

## Path B — Coolify

Paste the keys from `.env.prod.example` into the Coolify environment editor, filling
every `CHANGE_ME`. Keep your filled copy locally in `.env.prod` (gitignored) as the
paste source.

- Deploys via `docker-compose.coolify.yml` or `Dockerfile.app`.
- Add Persistent Storage mounted at `/app/data` so SQLite and preview builds survive
  redeploys.
- Set `PREVIEW_APP_MODEL` explicitly to a large-context model — Coolify can
  retain stale overrides, and `deepseek-chat` (32k) fails preflight on large
  prompts. See [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) for the models that
  actually produce good output.
- Pushing `main` auto-deploys when Coolify is connected to the repository.

## Local development

Unchanged — `docker compose up` + `backend/.env` (OpenRouter by default). See
[docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) for which env file feeds what.

Staging is retired. `docker-compose.staging.yml`, `scripts/verify-staging.sh`,
`.env.staging.example`, and `docs/operations/STAGING_DEPLOYMENT.md` were all
deleted along with the preview generator v2 stack they existed to exercise.
