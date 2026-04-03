FROM python:3.11-slim

LABEL maintainer="Jeremy Paulo Salvino Tabernero"
LABEL description="Guardian One — Multi-Agent AI Orchestration Platform"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create data and log directories
RUN mkdir -p data logs

# Default port for web dashboard / health API
EXPOSE 5000 8080

# Environment defaults
ENV PYTHONUNBUFFERED=1
ENV GUARDIAN_MASTER_PASSPHRASE=""

# Default: run all agents once
CMD ["python", "main.py"]
