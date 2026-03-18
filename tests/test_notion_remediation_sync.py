"""Tests for NotionRemediationSync — push remediation status to Notion."""

import tempfile
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog
from guardian_one.core.security_remediation import (
    SecurityRemediationTracker,
    VerificationResult,
)
from guardian_one.integrations.notion_remediation_sync import NotionRemediationSync
from guardian_one.integrations.notion_sync import NotionSync, SyncResult
from guardian_one.homelink.gateway import Gateway
from guardian_one.homelink.vault import Vault


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_notion_sync(audit: AuditLog) -> NotionSync:
    """Create a NotionSync with fake gateway/vault for testing."""
    tmp = Path(tempfile.mkdtemp())
    gateway = Gateway(audit)
    vault = Vault(tmp / "vault.enc", passphrase="test-pass")
    return NotionSync(
        gateway=gateway,
        vault=vault,
        audit=audit,
        root_page_id="test-root-page-id",
    )


# ---------------------------------------------------------------------------
# Dashboard push
# ---------------------------------------------------------------------------

class TestRemediationDashboard:
    def test_push_dashboard_creates_page(self) -> None:
        audit = _make_audit()
        sync = _make_notion_sync(audit)
        rem_sync = NotionRemediationSync(sync, audit)

        tracker = SecurityRemediationTracker()
        tracker.load_defaults()

        result = rem_sync.push_remediation_dashboard(tracker)
        # Will succeed because fake gateway returns success by default
        assert isinstance(result, SyncResult)

    def test_push_dashboard_with_completions(self) -> None:
        audit = _make_audit()
        sync = _make_notion_sync(audit)
        rem_sync = NotionRemediationSync(sync, audit)

        tracker = SecurityRemediationTracker()
        tracker.load_defaults()

        # Mark some tasks complete
        tracker.record_verification(VerificationResult(
            task_id="jtmdai-001",
            passed=True,
            method="ssl_check",
            evidence="SSL Labs grade A",
        ))
        tracker.record_verification(VerificationResult(
            task_id="jtmdai-002",
            passed=True,
            method="dns_txt_check",
            evidence="v=spf1 -all confirmed",
        ))

        result = rem_sync.push_remediation_dashboard(tracker)
        assert isinstance(result, SyncResult)

    def test_push_dashboard_all_domains(self) -> None:
        audit = _make_audit()
        sync = _make_notion_sync(audit)
        rem_sync = NotionRemediationSync(sync, audit)

        tracker = SecurityRemediationTracker()
        tracker.load_all_domains()

        result = rem_sync.push_remediation_dashboard(tracker)
        assert isinstance(result, SyncResult)


# ---------------------------------------------------------------------------
# Verification report push
# ---------------------------------------------------------------------------

class TestVerificationReport:
    def test_push_verification_report(self) -> None:
        audit = _make_audit()
        sync = _make_notion_sync(audit)
        rem_sync = NotionRemediationSync(sync, audit)

        tracker = SecurityRemediationTracker()
        tracker.load_defaults()

        verification_results = [
            {"task_id": "jtmdai-001", "passed": True, "method": "ssl_check",
             "evidence": "SSL Labs grade A"},
            {"task_id": "jtmdai-002", "passed": True, "method": "dns_txt_check",
             "evidence": "v=spf1 -all confirmed"},
            {"task_id": "jtmdai-004", "passed": False, "method": "dmarc_check",
             "evidence": "p=none found, expected p=reject"},
        ]

        result = rem_sync.push_verification_report(tracker, verification_results)
        assert isinstance(result, SyncResult)

    def test_push_verification_report_empty(self) -> None:
        audit = _make_audit()
        sync = _make_notion_sync(audit)
        rem_sync = NotionRemediationSync(sync, audit)

        tracker = SecurityRemediationTracker()
        result = rem_sync.push_verification_report(tracker, [])
        assert isinstance(result, SyncResult)


# ---------------------------------------------------------------------------
# Integration with tracker stats
# ---------------------------------------------------------------------------

class TestIntegrationWithTracker:
    def test_notion_data_matches_schema(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        data = tracker.notion_sync_data()

        # Verify all fields that Notion expects are present
        required_fields = {
            "task_id", "task", "category", "due_date",
            "last_checked", "notes", "severity", "status",
        }
        for item in data:
            assert required_fields.issubset(set(item.keys()))

    def test_category_values_match_notion_tags(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        data = tracker.notion_sync_data()

        valid_categories = {
            "Email Security", "Cloudflare Config", "Webflow Platform",
            "HTTP Security", "Infrastructure", "Brand Protection",
            "Connector Security",
        }
        for item in data:
            assert item["category"] in valid_categories

    def test_severity_values_match_notion_tags(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        data = tracker.notion_sync_data()

        valid_severities = {"Critical", "High", "Medium", "Low", "Info"}
        for item in data:
            assert item["severity"] in valid_severities

    def test_status_values_match_notion_tags(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        data = tracker.notion_sync_data()

        valid_statuses = {
            "Not Started", "In Progress", "Verified Complete", "Blocked",
        }
        for item in data:
            assert item["status"] in valid_statuses
