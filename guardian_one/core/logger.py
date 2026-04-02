"""Structured production logging — JSON-formatted operational logs.

Separate from the audit trail (which tracks agent decisions), this module
provides standard Python logging with structured JSON output suitable for
log aggregation (ELK, Loki, CloudWatch, etc.).

Usage:
    from guardian_one.core.logger import get_logger

    log = get_logger("cfo")
    log.info("Processing transactions", extra={"count": 42, "source": "plaid"})
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        # Merge extra structured fields (skip standard LogRecord attrs)
        _standard = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
        for key, val in record.__dict__.items():
            if key not in _standard and key not in payload:
                try:
                    json.dumps(val)  # ensure serializable
                    payload[key] = val
                except (TypeError, ValueError):
                    payload[key] = str(val)

        if record.exc_info and record.exc_info[1]:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    """Colored, human-readable output for console/development."""

    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[41m",  # red bg
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        msg = record.getMessage()
        return f"{color}{ts} [{record.levelname:<7}] {record.name}: {msg}{self.RESET}"


def _log_dir() -> Path:
    """Return the log directory, creating it if needed."""
    d = Path(os.getenv("GUARDIAN_LOG_DIR", "logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_logging(
    level: str = "INFO",
    json_output: bool = True,
    log_file: str = "guardian.log",
) -> None:
    """Configure the root Guardian One logger.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: Use JSON formatter for file output (True for prod).
        log_file: Name of the log file inside the log directory.
    """
    root = logging.getLogger("guardian_one")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Prevent duplicate handlers on re-init
    root.handlers.clear()

    # File handler — always JSON for machine parsing
    file_path = _log_dir() / log_file
    fh = logging.handlers.RotatingFileHandler(
        file_path, maxBytes=10 * 1024 * 1024, backupCount=5,
    )
    fh.setFormatter(JSONFormatter())
    root.addHandler(fh)

    # Console handler — human-friendly in dev, JSON in prod
    ch = logging.StreamHandler(sys.stderr)
    if json_output and os.getenv("GUARDIAN_ENV") == "production":
        ch.setFormatter(JSONFormatter())
    else:
        ch.setFormatter(HumanFormatter())
    ch.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(ch)


# Need to import handlers for RotatingFileHandler
import logging.handlers  # noqa: E402


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the guardian_one namespace.

    Args:
        name: Component name (e.g. "cfo", "gateway", "health").

    Returns:
        A configured Logger instance.
    """
    return logging.getLogger(f"guardian_one.{name}")
