"""Tests for structured logging module."""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from guardian_one.core.logging import (
    ConsoleFormatter,
    JSONFormatter,
    get_correlation_id,
    get_logger,
    set_correlation_id,
    _initialized,
)


@pytest.fixture(autouse=True)
def reset_logging_state():
    """Clean up between tests to avoid logger re-use and handler leaks."""
    yield
    # Clear initialized set so each test can create fresh loggers.
    for name in ("test_mod", "test_file", "test_console", "test_corr"):
        _initialized.discard(name)
        # Remove and close any handlers attached to the singleton logger
        logger = logging.getLogger(f"guardian.{name}")
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
    # Reset correlation ID.
    import guardian_one.core.logging as mod
    if hasattr(mod._context, "correlation_id"):
        del mod._context.correlation_id


# ------------------------------------------------------------------
# Correlation ID
# ------------------------------------------------------------------

def test_set_correlation_id_returns_id():
    cid = set_correlation_id("abc123")
    assert cid == "abc123"


def test_set_correlation_id_generates_default():
    cid = set_correlation_id()
    assert isinstance(cid, str)
    assert len(cid) == 12


def test_get_correlation_id_returns_set_value():
    set_correlation_id("xyz")
    assert get_correlation_id() == "xyz"


def test_get_correlation_id_returns_none_when_unset():
    assert get_correlation_id() is None


# ------------------------------------------------------------------
# JSONFormatter
# ------------------------------------------------------------------

def test_json_formatter_produces_valid_json():
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="guardian.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Hello %s",
        args=("world",),
        exc_info=None,
    )
    output = fmt.format(record)
    data = json.loads(output)
    assert data["level"] == "INFO"
    assert data["message"] == "Hello world"
    assert "timestamp" in data


def test_json_formatter_includes_correlation_id():
    set_correlation_id("corr-001")
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="guardian.test", level=logging.INFO,
        pathname="", lineno=0, msg="test", args=(), exc_info=None,
    )
    data = json.loads(fmt.format(record))
    assert data["correlation_id"] == "corr-001"


def test_json_formatter_includes_extra_fields():
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="guardian.test", level=logging.INFO,
        pathname="", lineno=0, msg="test", args=(), exc_info=None,
    )
    record.agent = "cfo"
    record.action = "sync"
    data = json.loads(fmt.format(record))
    assert data["agent"] == "cfo"
    assert data["action"] == "sync"


# ------------------------------------------------------------------
# ConsoleFormatter
# ------------------------------------------------------------------

def test_console_formatter_basic():
    fmt = ConsoleFormatter()
    record = logging.LogRecord(
        name="guardian.test", level=logging.INFO,
        pathname="", lineno=0, msg="Starting up", args=(), exc_info=None,
    )
    output = fmt.format(record)
    assert "INFO" in output
    assert "guardian.test" in output
    assert "Starting up" in output


def test_console_formatter_includes_correlation_id():
    set_correlation_id("req-42")
    fmt = ConsoleFormatter()
    record = logging.LogRecord(
        name="guardian.test", level=logging.WARNING,
        pathname="", lineno=0, msg="warn", args=(), exc_info=None,
    )
    output = fmt.format(record)
    assert "[req-42]" in output


# ------------------------------------------------------------------
# get_logger
# ------------------------------------------------------------------

def test_get_logger_returns_logger():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = get_logger("test_mod", log_dir=tmpdir)
        assert isinstance(logger, logging.Logger)
        assert logger.name == "guardian.test_mod"


def test_get_logger_creates_log_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = get_logger("test_file", log_dir=tmpdir)
        logger.info("test message")
        # Flush handlers.
        for h in logger.handlers:
            h.flush()
        log_file = Path(tmpdir) / "guardian.log"
        assert log_file.exists()
        content = log_file.read_text()
        data = json.loads(content.strip())
        assert data["message"] == "test message"


def test_get_logger_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger1 = get_logger("test_mod", log_dir=tmpdir)
        handler_count = len(logger1.handlers)
        logger2 = get_logger("test_mod", log_dir=tmpdir)
        assert logger1 is logger2
        assert len(logger2.handlers) == handler_count  # No duplicate handlers.
