"""Structured logging for Guardian One.

Usage:
    from guardian_one.core.logging import get_logger, set_correlation_id

    logger = get_logger("cfo")
    set_correlation_id("sync-20260323-001")
    logger.info("Starting sync cycle", extra={"accounts": 33})
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


_context = threading.local()

# Standard LogRecord attributes — anything not in this set was passed via extra={}
_LOG_RECORD_BUILTINS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
)


def set_correlation_id(correlation_id: str | None = None) -> str:
    """Set a correlation ID for the current thread. Returns the ID."""
    cid = correlation_id or uuid.uuid4().hex[:12]
    _context.correlation_id = cid
    return cid


def get_correlation_id() -> str | None:
    """Get the current thread's correlation ID."""
    return getattr(_context, "correlation_id", None)


class JSONFormatter(logging.Formatter):
    """Formats log records as JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        # Capture any user-supplied extra= fields (not in standard LogRecord)
        for key, val in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTINS and key not in log_entry:
                log_entry[key] = val
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        return json.dumps(log_entry, default=str)


class ConsoleFormatter(logging.Formatter):
    """Compact console output."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        cid = get_correlation_id()
        prefix = f"[{ts}] {record.levelname:7s}"
        if cid:
            prefix += f" [{cid}]"
        return f"{prefix} {record.name}: {record.getMessage()}"


_initialized: set[str] = set()
_init_lock = threading.Lock()


def get_logger(
    name: str,
    log_dir: str | Path = "logs",
    level: int = logging.DEBUG,
) -> logging.Logger:
    """Get or create a structured logger.

    File handler logs everything at DEBUG level as JSON.
    Console handler logs INFO and above in compact format.
    Thread-safe: guarded by _init_lock to prevent duplicate handlers.
    """
    logger = logging.getLogger(f"guardian.{name}")

    if name in _initialized:
        return logger

    with _init_lock:
        # Double-check under lock to prevent races
        if name in _initialized:
            return logger

        # Clear any stale handlers (e.g., from tests clearing _initialized)
        for h in logger.handlers[:]:
            h.close()
            logger.removeHandler(h)

        logger.setLevel(level)
        logger.propagate = False

        # File handler — JSON, daily rotation, 30 days
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_path / "guardian.log",
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JSONFormatter())
        logger.addHandler(file_handler)

        # Console handler — compact, INFO+
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(ConsoleFormatter())
        logger.addHandler(console_handler)

        _initialized.add(name)
    return logger
