# Guardian One — Multi-Agent AI Orchestration Platform
# Runs the daemon (--daemon) or web panel (--devpanel) or any CLI command.

FROM python:3.11-slim AS base

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system deps (cryptography needs these)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data and log directories
RUN mkdir -p /app/data /app/logs

# Expose ports: 5100 (web panel), 5200 (daemon health API)
EXPOSE 5100 5200

# Healthcheck against daemon health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5200/health || exit 1

# Default: run daemon + web panel together
CMD ["sh", "-c", "python main.py --daemon & exec python main.py --devpanel"]
