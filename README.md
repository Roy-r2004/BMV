# BMV · BuildMyVersion AI

Show us a tool you like. We'll design your business version.

A lead-generation web app where business owners describe their business, share a reference tool, and receive a custom MVP blueprint with a visual demo preview. Built for Roy's AI product-building service.

## Stack

- **Frontend:** React, Vite, TypeScript, Tailwind CSS, React Router, Axios
- **Backend:** Python, FastAPI, SQLite, SQLAlchemy, Pydantic, Jinja2 — see [`backend/ARCHITECTURE.md`](backend/ARCHITECTURE.md) for folder layout and request flow
- **AI:** **OpenRouter** (cloud API — default for local dev) or **Ollama** (self-hosted local models). Switch with `AI_PROVIDER` in `backend/.env`.

## Quick Start (Docker — recommended)

Everything runs in **one container**: React frontend, FastAPI backend, SQLite, uploads, and (optionally) Ollama for self-hosted AI.

**Using OpenRouter instead?** Set `AI_PROVIDER=openrouter` and `OPENROUTER_API_KEY` in `.env` — no local model downloads or GPU required.

### Requirements

- Docker Desktop (or Docker Engine + Compose)
- **OpenRouter:** API key only — no extra RAM for models
- **Ollama (optional):** ~8 GB RAM recommended; first start downloads AI models (~10 GB) — can take 15–30+ minutes

### Run

```bash
copy .env.example .env          # Windows
# cp .env.example .env          # macOS/Linux
# Edit .env — set ADMIN_PASSWORD and ROY_WHATSAPP_NUMBER

docker compose up --build
```

Open **http://localhost:8000**

- App UI: `/`
- Admin: `/admin/login`
- API health: `/api/health`

### Docker notes

| Item | Location |
|------|----------|
| SQLite DB | `buildmyversion-data` volume → `/app/data` |
| Uploads | same volume → `/app/data/uploads` |
| Ollama models | `ollama-models` volume → `/root/.ollama` |

Set `PULL_MODELS=false` in `.env` after the first successful run to skip model checks on restart.

```bash
docker compose down
docker compose up -d
```

---

## Production / Hostinger VPS (Docker + Traefik)

Default production path uses **OpenRouter** (no GPU). Good fit for Hostinger VPS (~2–4 GB RAM).

| Service | Role |
|---------|------|
| **Traefik** | Reverse proxy + Let's Encrypt TLS |
| **app** | React + FastAPI + Node (Vite preview builds) |
| **ollama** | Optional (`--profile ollama`) for self-hosted models |

### Requirements (OpenRouter — recommended)

- Hostinger (or any) Linux VPS with Docker + Compose
- Domain DNS → VPS IP (`A` for `DOMAIN` and `traefik.DOMAIN`)
- **2 GB+ RAM** (4 GB comfortable), OpenRouter API key

### Setup (Hostinger)

```bash
# On the VPS
git clone https://github.com/Roy-r2004/BMV.git
cd BMV
cp .env.prod.example .env
# Edit .env — DOMAIN, ACME_EMAIL, ADMIN_PASSWORD, OPENROUTER_API_KEY

docker compose -f docker-compose.prod.yml up -d --build
```

Open **https://your-domain.com** (app) and **https://traefik.your-domain.com** (Traefik dashboard).

### Optional: Ollama on a larger VPS (8 GB+)

```bash
# In .env: AI_PROVIDER=ollama (+ ollama model names)
docker compose -f docker-compose.prod.yml --profile ollama --profile init run --rm ollama-init
docker compose -f docker-compose.prod.yml --profile ollama up -d --build
```

### Production notes

| Item | Location |
|------|----------|
| SQLite DB + preview apps | `buildmyversion-data` volume |
| Ollama models (if used) | `ollama-models` volume |
| TLS certs | `traefik-certs` volume |

- Never commit real `.env` / API keys.
- Ollama (when enabled) is internal-only — not exposed publicly.

### Dev vs prod compose

| File | Use case |
|------|----------|
| `docker-compose.yml` | Local API (OpenRouter) + Vite frontend |
| `docker-compose.prod.yml` | Hostinger/VPS with Traefik + HTTPS |

---

## Local development (without Docker)

### Option A — OpenRouter (recommended)

No local GPU or model pulls. Create `backend/.env` from `backend/.env.example`, set:

```env
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
TEXT_MODEL=google/gemini-2.5-flash
PREVIEW_APP_MODEL=deepseek/deepseek-chat
V2_CANDIDATE_COMPONENT_MODEL=deepseek/deepseek-chat
V2_CANDIDATE_PAGE_MODEL=google/gemini-2.5-flash
CRITIC_MODEL=google/gemini-2.5-flash
FIX_MODEL=google/gemini-2.5-flash
```

Then start backend + frontend (steps 2–3 below).

### Option B — Ollama (self-hosted)

```bash
ollama serve
ollama pull llama3.2-vision
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b
```

Set `AI_PROVIDER=ollama` in `backend/.env`.

### 2. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
npm run dev
```

Open http://localhost:5173

## Environment Variables

Local Docker uses:

| File | Purpose |
|------|---------|
| `backend/.env` | **Source of truth** — API keys, models, AppSpec, preview flags |
| `frontend/.env` | Vite only (`VITE_*`) |

```bash
cp backend/.env.example backend/.env
# edit backend/.env
cp frontend/.env.example frontend/.env   # optional if missing
```

Production/VPS uses root `.env` from `.env.prod.example` (separate from local).

**Backend** (`backend/.env`) essentials:

```env
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
ADMIN_PASSWORD=change_this_password
```

**Frontend** (`frontend/.env`):

```env
VITE_API_BASE_URL=http://localhost:8001
```

## Pages

| Route | Description |
|-------|-------------|
| `/` | Landing page |
| `/submit` | Business request form |
| `/result/:id` | Public preview with visual demo |
| `/admin/login` | Admin password login |
| `/admin` | Request dashboard |
| `/admin/requests/:id` | Request detail & AI controls |

## Admin

Default password is set in `ADMIN_PASSWORD` env var. Admin can:

- View all requests with status filters
- Run AI generation pipeline (screenshot analysis, blueprint, visual demo, technical plan, proposal)
- Edit proposals and notes
- Copy proposal and WhatsApp follow-up messages

## AI Pipeline

On form submit, the system automatically runs the full AI pipeline:

1. Fetch reference URL metadata
2. Analyze uploaded screenshot (if image)
3. Generate MVP blueprint
4. Generate visual demo JSON
5. Build React preview app (or HTML role pages fallback)
6. Generate technical plan
7. Generate client proposal

Models are chosen from `backend/.env` (`TEXT_MODEL`, `PREVIEW_APP_MODEL`, `VISION_MODEL`, etc.) based on `AI_PROVIDER` (OpenRouter or Ollama).

If the AI provider is unavailable, the request is still saved and admin can regenerate later.

## Legal

This tool does not copy proprietary code, designs, or brand assets. References are used only to understand the desired workflow or experience, then a custom version is designed for the client's business.
