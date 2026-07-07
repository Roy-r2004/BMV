# App-only image for production (Ollama runs in a separate container)
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
    OLLAMA_URL=http://ollama:11434 \
    PORT=8000 \
    PULL_MODELS=false

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Post-build visual critique needs a real browser to screenshot the rendered
# app. --with-deps pulls in the OS-level libs Chromium needs on Debian slim.
# --no-shell skips the separate chromium-headless-shell binary — screenshot.py
# launches with channel="chromium" (Chromium's "new" headless mode), which
# reuses the regular Chromium build instead. This is still a real size/latency
# cost of this feature: adds ~200-300MB to the image and roughly a minute to
# the build — not free, flagging it here rather than hiding it in a base
# image bump.
RUN playwright install --with-deps --no-shell chromium

COPY backend/app ./app
COPY --from=frontend-build /app/frontend/dist /app/static
COPY docker/entrypoint.app.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh \
    && mkdir -p /app/data/uploads

VOLUME ["/app/data"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
