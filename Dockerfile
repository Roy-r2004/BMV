# Frontend build
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

# Runtime: Ollama + FastAPI + static frontend
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    DATABASE_URL=sqlite:////app/data/buildmyversion.db \
    UPLOAD_DIR=/app/data/uploads \
    STATIC_DIR=/app/static \
    OLLAMA_URL=http://127.0.0.1:11434 \
    OLLAMA_HOST=0.0.0.0:11434 \
    PORT=8000 \
    PULL_MODELS=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    zstd \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend-build /app/frontend/dist /app/static
COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh \
    && mkdir -p /app/data/uploads

VOLUME ["/app/data", "/root/.ollama"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
