"""Tests for the centralized PII content gate."""

import os
import tempfile
from pathlib import Path
from unittest import mock

from guardian_one.core.content_gate import (
    _DEPTH_EXCEEDED_SENTINEL,
    contains_pii,
    redact_dict,
    redact_text,
    scan_pii,
)
from guardian_one.core.audit import AuditLog


# ---------------------------------------------------------------------------
# Helper: set owner env vars for tests that need owner-pattern matching
# ---------------------------------------------------------------------------

_OWNER_ENV = {
    "GUARDIAN_OWNER_NAMES": (
        "Jeremy Paulo Salvino Tabernero|Jeremy Tabernero|"
        "Jeremy Paulo Tabernero|J. Tabernero|"
        "JEREMY TABERNERO|JEREMY PAULO TABERNERO|"
        "jeremytabernero|jeremy_paulo21|JEREMY_PAULO21"
    ),
    "GUARDIAN_OWNER_EMAILS": (
        "jeremytabernero@gmail.com|jeremy_paulo21@yahoo.com"
    ),
}


def _reload_owner_patterns():
    """Reload the content gate module so owner patterns pick up new env vars."""
    import importlib
    import guardian_one.core.content_gate as cg
    importlib.reload(cg)
    # Re-import functions from reloaded module
    return cg.redact_text, cg.redact_dict, cg.contains_pii, cg.scan_pii


# ---------------------------------------------------------------------------
# redact_text — general PII patterns
# ---------------------------------------------------------------------------


class TestRedactText:
    def test_email_redacted(self):
        text = "Contact us at user@example.com for help"
        result = redact_text(text, include_owner=False)
        assert "user@example.com" not in result
        assert "[EMAIL-REDACTED]" in result

    def test_ssn_redacted(self):
        text = "SSN is 123-45-6789"
        result = redact_text(text, include_owner=False)
        assert "123-45-6789" not in result
        assert "[SSN-REDACTED]" in result

    def test_credit_card_redacted(self):
        text = "Card: 4111 1111 1111 1111"
        result = redact_text(text, include_owner=False)
        assert "4111 1111 1111 1111" not in result
        assert "[CARD-REDACTED]" in result

    def test_phone_redacted(self):
        text = "Call (555) 123-4567 for info"
        result = redact_text(text, include_owner=False)
        assert "(555) 123-4567" not in result
        assert "[PHONE-REDACTED]" in result

    def test_bank_account_redacted(self):
        text = "Account #: 123456789012"
        result = redact_text(text, include_owner=False)
        assert "123456789012" not in result
        assert "[ACCOUNT-REDACTED]" in result

    def test_mrn_redacted(self):
        text = "MRN: 12345678"
        result = redact_text(text, include_owner=False)
        assert "12345678" not in result
        assert "[MRN-REDACTED]" in result

    def test_empty_string(self):
        assert redact_text("") == ""
        assert redact_text("", include_owner=True) == ""

    def test_safe_text_unchanged(self):
        text = "The weather is nice today"
        assert redact_text(text, include_owner=False) == text


# ---------------------------------------------------------------------------
# redact_text — owner-specific patterns (loaded from env)
# ---------------------------------------------------------------------------


class TestOwnerRedaction:
    def test_owner_full_name_redacted(self):
        with mock.patch.dict(os.environ, _OWNER_ENV):
            rt, *_ = _reload_owner_patterns()
            text = "Dear JEREMY TABERNERO, your receipt is attached"
            result = rt(text)
            assert "JEREMY TABERNERO" not in result
            assert "[OWNER-NAME-REDACTED]" in result

    def test_owner_email_redacted(self):
        with mock.patch.dict(os.environ, _OWNER_ENV):
            rt, *_ = _reload_owner_patterns()
            text = "Sent to jeremytabernero@gmail.com"
            result = rt(text)
            assert "jeremytabernero@gmail.com" not in result
            assert "[OWNER-EMAIL-REDACTED]" in result

    def test_owner_yahoo_email_redacted(self):
        with mock.patch.dict(os.environ, _OWNER_ENV):
            rt, *_ = _reload_owner_patterns()
            text = "This email was sent to JEREMY_PAULO21@YAHOO.COM"
            result = rt(text)
            assert "JEREMY_PAULO21@YAHOO.COM" not in result

    def test_owner_name_case_insensitive(self):
        with mock.patch.dict(os.environ, _OWNER_ENV):
            rt, *_ = _reload_owner_patterns()
            text = "Jeremy Tabernero signed up"
            result = rt(text)
            assert "Jeremy Tabernero" not in result

    def test_owner_disabled(self):
        text = "jeremytabernero@gmail.com"
        result = redact_text(text, include_owner=False)
        # Still caught by the general email pattern
        assert "jeremytabernero@gmail.com" not in result
        assert "[EMAIL-REDACTED]" in result

    def test_no_owner_patterns_without_env(self):
        """Without env vars, owner patterns are empty — no owner redaction."""
        with mock.patch.dict(os.environ, {}, clear=True):
            rt, *_ = _reload_owner_patterns()
            text = "Jeremy Tabernero"
            result = rt(text)
            # No owner patterns loaded, so the name passes through
            assert result == text


# ---------------------------------------------------------------------------
# redact_dict — recursive dict redaction
# ---------------------------------------------------------------------------


class TestRedactDict:
    def test_flat_dict(self):
        data = {"sender": "user@example.com", "count": 5}
        result = redact_dict(data, include_owner=False)
        assert "[EMAIL-REDACTED]" in result["sender"]
        assert result["count"] == 5

    def test_nested_dict(self):
        data = {"outer": {"inner": "SSN 123-45-6789"}}
        result = redact_dict(data, include_owner=False)
        assert "123-45-6789" not in result["outer"]["inner"]

    def test_list_in_dict(self):
        data = {"emails": ["a@b.com", "c@d.com"]}
        result = redact_dict(data, include_owner=False)
        assert all("[EMAIL-REDACTED]" in e for e in result["emails"])

    def test_empty_dict(self):
        assert redact_dict({}) == {}

    def test_depth_limit_fails_closed_dict(self):
        """Nested dicts beyond depth limit are replaced with sentinel."""
        # Build a structure 12 levels deep with PII at the bottom
        data: dict = {"pii": "secret@evil.com"}
        for _ in range(12):
            data = {"nested": data}
        result = redact_dict(data, include_owner=False)
        # The over-depth nested dict should be replaced with sentinel
        cursor = result
        for _ in range(11):
            cursor = cursor["nested"]
        assert cursor["nested"] == _DEPTH_EXCEEDED_SENTINEL

    def test_depth_limit_redacts_strings_at_boundary(self):
        """Strings at the depth boundary are still redacted, not leaked."""
        data: dict = {"email": "leak@example.com"}
        for _ in range(11):
            data = {"nested": data}
        result = redact_dict(data, include_owner=False)
        cursor = result
        for _ in range(11):
            cursor = cursor["nested"]
        # The string at depth 11 should be redacted, not raw
        assert "leak@example.com" not in cursor["email"]

    def test_depth_limit_fails_closed_list(self):
        """Nested lists beyond depth limit are replaced with sentinel."""
        data: dict = {"items": [{"pii": "secret@evil.com"}]}
        for _ in range(12):
            data = {"nested": data}
        result = redact_dict(data, include_owner=False)
        cursor = result
        for _ in range(11):
            cursor = cursor["nested"]
        # The list at over-depth should be replaced with sentinel
        assert cursor["nested"] == _DEPTH_EXCEEDED_SENTINEL


# ---------------------------------------------------------------------------
# contains_pii
# ---------------------------------------------------------------------------


class TestContainsPii:
    def test_detects_email(self):
        assert contains_pii("email: test@example.com", include_owner=False)

    def test_detects_ssn(self):
        assert contains_pii("SSN 123-45-6789", include_owner=False)

    def test_detects_owner_name(self):
        with mock.patch.dict(os.environ, _OWNER_ENV):
            _, _, cp, _ = _reload_owner_patterns()
            assert cp("Dear Jeremy Tabernero")

    def test_safe_text(self):
        assert not contains_pii("The weather is nice", include_owner=False)

    def test_empty(self):
        assert not contains_pii("")


# ---------------------------------------------------------------------------
# scan_pii
# ---------------------------------------------------------------------------


class TestScanPii:
    def test_returns_findings(self):
        text = "Email user@test.com, SSN 123-45-6789"
        findings = scan_pii(text, include_owner=False)
        types = {f["type"] for f in findings}
        assert "email" in types
        assert "ssn" in types

    def test_no_findings_for_safe_text(self):
        assert scan_pii("hello world", include_owner=False) == []

    def test_owner_findings(self):
        with mock.patch.dict(os.environ, _OWNER_ENV):
            _, _, _, sp = _reload_owner_patterns()
            findings = sp("Jeremy Tabernero")
            assert any(f["type"] == "owner_name" for f in findings)


# ---------------------------------------------------------------------------
# Audit log integration — PII is redacted before hitting disk
# ---------------------------------------------------------------------------


class TestAuditPiiRedaction:
    def test_audit_redacts_email_in_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(log_dir=Path(tmpdir))
            log.record(
                agent="gmail_agent",
                action="inbox_checked",
                details={"sender": "victim@example.com"},
            )
            entry = log.query(agent="gmail_agent")[0]
            assert "victim@example.com" not in entry.details["sender"]
            assert "[EMAIL-REDACTED]" in entry.details["sender"]

    def test_audit_redacts_owner_email_in_action(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(log_dir=Path(tmpdir))
            log.record(
                agent="gmail_agent",
                action="monitoring jeremytabernero@gmail.com",
            )
            entry = log.query(agent="gmail_agent")[0]
            # The general email pattern catches this even without owner env
            assert "jeremytabernero@gmail.com" not in entry.action

    def test_audit_redacts_ssn_in_details(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(log_dir=Path(tmpdir))
            log.record(
                agent="archivist",
                action="data_processed",
                details={"content": "SSN is 123-45-6789"},
            )
            entry = log.query(agent="archivist")[0]
            assert "123-45-6789" not in entry.details["content"]

    def test_audit_preserves_non_pii(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(log_dir=Path(tmpdir))
            log.record(
                agent="chronos",
                action="schedule_updated",
                details={"event": "Team meeting", "count": 3},
            )
            entry = log.query(agent="chronos")[0]
            assert entry.details["event"] == "Team meeting"
            assert entry.details["count"] == 3
            assert entry.action == "schedule_updated"
