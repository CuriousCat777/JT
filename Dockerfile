# Guardian One — Production Container
# ====================================
# Multi-stage build: slim Python image with only runtime deps.
# Database (SQLite) persisted via Docker volume.
#
# Build:  docker build -t guardian-one .
# Run:    docker run -v guardian-data:/app/data -v guardian-logs:/app/logs \
#                    --env-file .env guardian-one
# Or use: docker compose up

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user for security
RUN groupadd --gid 1000 guardian && \
    useradd --uid 1000 --gid guardian --shell /bin/bash --create-home guardian

WORKDIR /app

# Install system dependencies (cryptography needs these)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Dependencies stage — cached layer for pip install
# ---------------------------------------------------------------------------
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Application stage
# ---------------------------------------------------------------------------
FROM deps AS app

# Copy application code
COPY guardian_one/ guardian_one/
COPY main.py .
COPY pyproject.toml .
COPY config/ config/
COPY docker-entrypoint.sh .

# Create data and log directories (will be mounted as volumes)
RUN mkdir -p data logs && \
    chown -R guardian:guardian /app

# Switch to non-root user
USER guardian

# Health check — verify the database is accessible
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "from guardian_one.database import GuardianDatabase; db = GuardianDatabase(); print(db.stats())" || exit 1

# Entrypoint auto-initializes DB on first run
ENTRYPOINT ["bash", "docker-entrypoint.sh"]
CMD ["--db"]

# Expose Flask web panel port (if using --devpanel)
EXPOSE 5100
