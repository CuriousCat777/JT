"""Tests for the centralized PII content gate."""

import tempfile
from pathlib import Path

from guardian_one.core.content_gate import (
    contains_pii,
    redact_dict,
    redact_text,
    scan_pii,
)
from guardian_one.core.audit import AuditLog, Severity


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
# redact_text — owner-specific patterns
# ---------------------------------------------------------------------------


class TestOwnerRedaction:
    def test_owner_full_name_redacted(self):
        text = "Dear JEREMY TABERNERO, your receipt is attached"
        result = redact_text(text)
        assert "JEREMY TABERNERO" not in result
        assert "[OWNER-NAME-REDACTED]" in result

    def test_owner_email_redacted(self):
        text = "Sent to jeremytabernero@gmail.com"
        result = redact_text(text)
        assert "jeremytabernero@gmail.com" not in result
        assert "[OWNER-EMAIL-REDACTED]" in result

    def test_owner_yahoo_email_redacted(self):
        text = "This email was sent to JEREMY_PAULO21@YAHOO.COM"
        result = redact_text(text)
        assert "JEREMY_PAULO21@YAHOO.COM" not in result

    def test_owner_name_case_insensitive(self):
        text = "Jeremy Tabernero signed up"
        result = redact_text(text)
        assert "Jeremy Tabernero" not in result

    def test_owner_disabled(self):
        text = "jeremytabernero@gmail.com"
        result = redact_text(text, include_owner=False)
        # Still caught by the general email pattern
        assert "jeremytabernero@gmail.com" not in result
        assert "[EMAIL-REDACTED]" in result


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


# ---------------------------------------------------------------------------
# contains_pii
# ---------------------------------------------------------------------------


class TestContainsPii:
    def test_detects_email(self):
        assert contains_pii("email: test@example.com", include_owner=False)

    def test_detects_ssn(self):
        assert contains_pii("SSN 123-45-6789", include_owner=False)

    def test_detects_owner_name(self):
        assert contains_pii("Dear Jeremy Tabernero")

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
        findings = scan_pii("Jeremy Tabernero")
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
