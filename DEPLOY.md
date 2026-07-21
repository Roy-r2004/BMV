# Deploy

**Hostinger VPS + OpenRouter (recommended):** see [docs/deploy/hostinger-openrouter.md](docs/deploy/hostinger-openrouter.md).

Quick path:

```bash
cp .env.prod.example .env
# edit DOMAIN, ACME_EMAIL, ADMIN_PASSWORD, OPENROUTER_API_KEY
bash scripts/deploy/hostinger-up.sh
```

Local development still uses `docker compose up` + `backend/.env` (also OpenRouter by default).
