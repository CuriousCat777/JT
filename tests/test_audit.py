"""Tests for the audit logging module."""

import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog, Severity


def test_record_and_query():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = AuditLog(log_dir=Path(tmpdir))
        log.record(agent="chronos", action="event_added", severity=Severity.INFO)
        log.record(agent="cfo", action="bill_alert", severity=Severity.WARNING)
        log.record(agent="chronos", action="conflict_detected", severity=Severity.ERROR)

        all_entries = log.query()
        assert len(all_entries) == 3

        chronos_only = log.query(agent="chronos")
        assert len(chronos_only) == 2

        warnings = log.query(severity=Severity.WARNING)
        assert len(warnings) == 1
        assert warnings[0].agent == "cfo"


def test_pending_reviews():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = AuditLog(log_dir=Path(tmpdir))
        log.record(agent="guardian_one", action="normal_op")
        log.record(agent="mediator", action="conflict", requires_review=True)

        pending = log.pending_reviews()
        assert len(pending) == 1
        assert pending[0].action == "conflict"


def test_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        log = AuditLog(log_dir=Path(tmpdir))
        log.record(agent="test", action="action_1")
        log.record(agent="test", action="action_2")

        summary = log.summary()
        assert "action_1" in summary
        assert "action_2" in summary


def test_load_from_disk():
    with tempfile.TemporaryDirectory() as tmpdir:
        log1 = AuditLog(log_dir=Path(tmpdir))
        log1.record(agent="test", action="persisted_action")

        log2 = AuditLog(log_dir=Path(tmpdir))
        assert len(log2.query()) == 0  # Not loaded yet
        log2.load_from_disk()
        assert len(log2.query()) == 1
        assert log2.query()[0].action == "persisted_action"
