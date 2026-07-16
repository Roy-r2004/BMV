# Production app image: React static + FastAPI + Node (Vite preview builds) + Playwright
# Ollama is optional (separate compose profile). Prefer AI_PROVIDER=openrouter on Hostinger.

FROM node:20-alpine AS frontend-build

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
    OLLAMA_URL=http://ollama:11434 \
    PORT=8000 \
    PULL_MODELS=false \
    PATH="/opt/node/bin:${PATH}"

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
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps --no-shell chromium

# Full backend (app + templates + preview-template for codegen/vite builds)
COPY backend/ ./
COPY --from=frontend-build /app/frontend/dist /app/static
COPY docker/entrypoint.app.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh \
    && mkdir -p /app/data/uploads /app/data/preview-apps \
    && test -f preview-template/package.json

VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
