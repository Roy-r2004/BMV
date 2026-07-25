# Production app image: React static + FastAPI + Node (Vite preview builds) + Playwright
# Ollama is optional (separate compose profile). Prefer AI_PROVIDER=openrouter on Hostinger.

# Frontend toolchain needs Node >= 22 (Vite 8 / current npm engines).
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

ARG VITE_API_BASE_URL=
ARG VITE_ROY_WHATSAPP_NUMBER=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_ROY_WHATSAPP_NUMBER=$VITE_ROY_WHATSAPP_NUMBER

RUN npm run build

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    DATABASE_URL=sqlite:////app/data/buildmyversion.db \
    UPLOAD_DIR=/app/data/uploads \
    STATIC_DIR=/app/static \
    PREVIEW_TEMPLATE_DIR=/app/backend/preview-template \
    PREVIEW_APPS_DIR=/app/data/preview-apps \
    PREVIEW_CANDIDATES_DIR=/app/data/preview-candidates \
    PREVIEW_VALIDATIONS_DIR=/app/data/runtime-validation \
    OLLAMA_URL=http://ollama:11434 \
    PORT=8000 \
    PULL_MODELS=false \
    SEED_DEMO=false \
    APP_ENV=production \
    PATH="/opt/node/bin:${PATH}" \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    xz-utils \
    && curl -fsSL https://nodejs.org/dist/v22.14.0/node-v22.14.0-linux-x64.tar.xz \
      | tar -xJ -C /opt \
    && mv /opt/node-v22.14.0-linux-x64 /opt/node \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Separate layer + retry: Coolify often kills this step on flaky downloads / OOM.
RUN playwright install-deps chromium \
    && (playwright install --no-shell chromium \
        || (sleep 5 && playwright install --no-shell chromium) \
        || (sleep 10 && playwright install --no-shell chromium))

# Full backend (app + templates + preview-template for codegen/vite builds)
COPY backend/ ./
COPY --from=frontend-build /app/frontend/dist /app/static
COPY docker/entrypoint.app.sh /entrypoint.sh
# Runtime validation + candidate builds invoke tsc/vite from the template
# node_modules tree. Without this install the image only has package.json.
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh \
    && mkdir -p /app/data/uploads /app/data/preview-apps \
      /app/data/preview-candidates /app/data/runtime-validation \
    && test -f preview-template/package.json \
    && test -f preview-template/package-lock.json \
    && npm ci --prefix preview-template \
    && test -f preview-template/node_modules/typescript/package.json \
    && test -f preview-template/node_modules/vite/package.json

VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=8 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
