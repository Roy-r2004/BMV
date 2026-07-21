# Deploy BuildMyVersion on Hostinger (OpenRouter)

Production stack: **Traefik (HTTPS) + App**. AI runs on **OpenRouter** — no Ollama, no GPU.

## Requirements

| Item | Recommendation |
|------|----------------|
| Hostinger plan | **VPS (KVM)** with Docker — not shared hosting |
| RAM | **4 GB minimum** (8 GB better for parallel previews) |
| Disk | 40 GB+ SSD |
| OS | Ubuntu 22.04 / 24.04 |
| Domain | A-record → VPS public IP (ports **80** and **443** open) |
| AI | [OpenRouter](https://openrouter.ai) API key with credit |

Do **not** enable the `ollama` compose profile on a small Hostinger VPS.

## 1. Server prep

```bash
# SSH into the VPS
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl git ufw

# Docker Engine + Compose plugin (official install)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# log out / back in so docker works without sudo

# Firewall
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

Point DNS: `A` record for `yourdomain.com` → VPS IP. Wait until it resolves.

## 2. Get the code

```bash
git clone https://github.com/Roy-r2004/BMV.git
cd BMV
git checkout main
```

## 3. Configure `.env`

```bash
cp .env.prod.example .env
nano .env   # or vim
```

Fill at least:

- `DOMAIN` — e.g. `app.yourdomain.com` or apex
- `ACME_EMAIL` — Let's Encrypt contact
- `ADMIN_PASSWORD` — strong password for `/admin`
- `OPENROUTER_API_KEY` — from OpenRouter dashboard
- `OPENROUTER_SITE_URL` — `https://YOUR_DOMAIN`
- `ROY_WHATSAPP_NUMBER` — digits only, country code, no `+`
- `PEXELS_API_KEY` — optional but recommended for imagery

Leave `AI_PROVIDER=openrouter`. Do not set Ollama vars.

## 4. Launch

```bash
# Validate + build + start
bash scripts/deploy/hostinger-up.sh

# Or manually:
docker compose -f docker-compose.prod.yml up -d --build
```

First build takes several minutes (Node, Playwright Chromium, Python deps).

## 5. Smoke checks

```bash
docker compose -f docker-compose.prod.yml ps
curl -sS https://YOUR_DOMAIN/api/health
curl -sS https://YOUR_DOMAIN/api/ai/status
```

Expect health `{"status":"ok"}` and AI status showing **openrouter** ready.

Then open:

- Site: `https://YOUR_DOMAIN`
- Admin: `https://YOUR_DOMAIN/admin` (password = `ADMIN_PASSWORD`)

Submit one test preview end-to-end before announcing go-live.

## 6. Day-2 ops

```bash
# Logs
docker compose -f docker-compose.prod.yml logs -f app

# Update from git
git pull
docker compose -f docker-compose.prod.yml up -d --build

# Backup SQLite + uploads (data volume)
docker run --rm -v buildmyversion-prod_buildmyversion-data:/data -v "$PWD:/backup" alpine \
  tar czf /backup/bmv-data-$(date +%F).tgz -C /data .
```

Volume name may vary — check with `docker volume ls | grep buildmyversion`.

## Architecture notes

- Frontend is built into the app image (`Dockerfile.app`); Traefik terminates TLS.
- Preview apps + SQLite live in Docker volume `buildmyversion-data`.
- Client never sees public package prices; build plans are AI JSON from the pipeline.
- Proposal markdown stays **admin-only**; not on the customer preview API.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Certificate pending | DNS not pointing yet; wait / check Traefik logs |
| AI failures | Key missing/invalid; check OpenRouter credits; `docker compose ... logs app` |
| OOM / killed builds | Upgrade VPS RAM; lower `PREVIEW_PARALLEL_WORKERS=1` |
| 502 from Traefik | App still starting (`start_period`); check `docker compose ps` |

## Security reminders

- Never commit `.env` (gitignored).
- Rotate any OpenRouter key that was pasted into chat or screenshots.
- Change `ADMIN_PASSWORD` from the example.
- Prefer restricting Traefik dashboard (`traefik.YOUR_DOMAIN`) or leave unused.
