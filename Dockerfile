# Guardian One — Multi-stage production Dockerfile
# Stage 1: Python agent engine
# Stage 2: React frontend build
# Stage 3: Ruby on Rails API (future)
# Final: Unified runtime

# ── Stage 1: Python backend ──────────────────────────────────────────
FROM python:3.11-slim AS python-base

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY guardian_one/ guardian_one/
COPY main.py mcp_server.py guardian_handoff_pipe.py ./
COPY config/ config/
COPY data/ data/

# Verify Python imports resolve
RUN python -c "import guardian_one; print('Guardian One: OK')"

# ── Stage 2: React frontend build ────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /app/greg/client

COPY greg/client/package*.json ./
RUN npm ci --production=false

COPY greg/client/ .
RUN npm run build || echo "WARN: React build not yet configured for production"

# ── Stage 3: Production runtime ──────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python application
COPY --from=python-base /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-base /app /app

# Copy React build output (served by Python Flask or Rails)
COPY --from=frontend-build /app/greg/client/dist /app/static/frontend

# Create non-root user
RUN groupadd -r guardian && useradd -r -g guardian guardian && \
    chown -R guardian:guardian /app
USER guardian

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import guardian_one; print('healthy')" || exit 1

EXPOSE 5100 8080

# Default: run all agents once
CMD ["python", "main.py"]
