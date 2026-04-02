"""Tests for the structured production logging module."""

import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from guardian_one.core.logger import (
    JSONFormatter,
    HumanFormatter,
    get_logger,
    setup_logging,
)


class TestJSONFormatter:
    """Tests for JSON log output."""

    def test_basic_format(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="guardian_one.cfo",
            level=logging.INFO,
            pathname="cfo.py",
            lineno=42,
            msg="Processing transactions",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["logger"] == "guardian_one.cfo"
        assert data["message"] == "Processing transactions"
        assert data["line"] == 42
        assert "ts" in data

    def test_extra_fields_included(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="guardian_one.cfo",
            level=logging.INFO,
            pathname="cfo.py",
            lineno=10,
            msg="Sync done",
            args=(),
            exc_info=None,
        )
        record.count = 42
        record.source = "plaid"
        output = formatter.format(record)
        data = json.loads(output)
        assert data["count"] == 42
        assert data["source"] == "plaid"

    def test_exception_included(self):
        formatter = JSONFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="guardian_one.test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Something failed",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "ValueError" in data["exception"]

    def test_non_serializable_extra(self):
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="test", args=(), exc_info=None,
        )
        record.custom_obj = object()
        output = formatter.format(record)
        data = json.loads(output)
        assert "custom_obj" in data  # should be str(object)


class TestHumanFormatter:
    """Tests for human-readable console output."""

    def test_basic_format(self):
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="guardian_one.cfo",
            level=logging.INFO,
            pathname="cfo.py",
            lineno=10,
            msg="All good",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "INFO" in output
        assert "guardian_one.cfo" in output
        assert "All good" in output

    def test_color_codes_present(self):
        formatter = HumanFormatter()
        for level in [logging.DEBUG, logging.WARNING, logging.ERROR, logging.CRITICAL]:
            record = logging.LogRecord(
                name="test", level=level, pathname="",
                lineno=0, msg="test", args=(), exc_info=None,
            )
            output = formatter.format(record)
            assert "\033[" in output  # ANSI escape present


class TestGetLogger:
    """Tests for the get_logger factory."""

    def test_returns_child_logger(self):
        log = get_logger("cfo")
        assert log.name == "guardian_one.cfo"

    def test_different_names_different_loggers(self):
        log1 = get_logger("cfo")
        log2 = get_logger("chronos")
        assert log1 is not log2
        assert log1.name != log2.name


class TestSetupLogging:
    """Tests for the setup_logging function."""

    def test_configures_root_logger(self, tmp_path):
        with patch.dict(os.environ, {"GUARDIAN_LOG_DIR": str(tmp_path)}):
            setup_logging(level="DEBUG", log_file="test.log")
            root = logging.getLogger("guardian_one")
            assert root.level == logging.DEBUG
            assert len(root.handlers) >= 2  # file + console

    def test_log_file_created(self, tmp_path):
        with patch.dict(os.environ, {"GUARDIAN_LOG_DIR": str(tmp_path)}):
            setup_logging(level="INFO", log_file="guardian_test.log")
            log = get_logger("test")
            log.info("Hello from test")
            # Flush handlers
            for h in logging.getLogger("guardian_one").handlers:
                h.flush()
            log_file = tmp_path / "guardian_test.log"
            assert log_file.exists()
            content = log_file.read_text()
            assert "Hello from test" in content
