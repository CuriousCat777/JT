"""Tests for SecurityRemediationTracker and Notion remediation sync."""

import tempfile
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog
from guardian_one.core.security_remediation import (
    CATEGORY_AGENT_MAP,
    RemediationCategory,
    RemediationSeverity,
    RemediationStatus,
    RemediationTask,
    SecurityRemediationTracker,
    VerificationResult,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


# ---------------------------------------------------------------------------
# Tracker — loading and querying
# ---------------------------------------------------------------------------

class TestTrackerLoading:
    def test_load_defaults_loads_16_jtmdai_tasks(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        assert len(tracker.all_tasks()) == 16

    def test_load_all_domains(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_all_domains()
        tasks = tracker.all_tasks()
        assert len(tasks) == 21  # 16 jtmdai + 5 drjt

    def test_load_domain_defaults_jtmdai(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_domain_defaults("jtmdai.com")
        assert len(tracker.all_tasks()) == 16

    def test_load_domain_defaults_drjt(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_domain_defaults("drjeremytabernero.org")
        assert len(tracker.all_tasks()) == 5

    def test_load_domain_defaults_unknown(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_domain_defaults("unknown.com")
        assert len(tracker.all_tasks()) == 0

    def test_domains_returns_unique_domains(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_all_domains()
        domains = tracker.domains()
        assert "jtmdai.com" in domains
        assert "drjeremytabernero.org" in domains
        assert len(domains) == 2


class TestTrackerQuerying:
    def test_tasks_by_domain(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_all_domains()
        jtmdai = tracker.tasks_by_domain("jtmdai.com")
        assert len(jtmdai) == 16
        drjt = tracker.tasks_by_domain("drjeremytabernero.org")
        assert len(drjt) == 5

    def test_tasks_by_category(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        email = tracker.tasks_by_category(RemediationCategory.EMAIL_SECURITY)
        assert len(email) >= 3  # SPF, DKIM, DMARC

    def test_tasks_by_severity(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        critical = tracker.tasks_by_severity(RemediationSeverity.CRITICAL)
        assert len(critical) == 1  # SSL/TLS Full Strict

    def test_tasks_by_status_all_not_started(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        not_started = tracker.tasks_by_status(RemediationStatus.NOT_STARTED)
        assert len(not_started) == 16

    def test_tasks_by_agent(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        wa_tasks = tracker.tasks_by_agent("web_architect")
        assert len(wa_tasks) >= 5
        arch_tasks = tracker.tasks_by_agent("archivist")
        assert len(arch_tasks) >= 2

    def test_auto_verifiable_tasks(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        auto = tracker.auto_verifiable_tasks()
        assert len(auto) >= 7

    def test_get_task_by_id(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        task = tracker.get_task("jtmdai-001")
        assert task is not None
        assert task.severity == RemediationSeverity.CRITICAL

    def test_get_task_not_found(self) -> None:
        tracker = SecurityRemediationTracker()
        assert tracker.get_task("nonexistent") is None


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

class TestVerification:
    def test_record_verification_pass(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()

        result = VerificationResult(
            task_id="jtmdai-002",
            passed=True,
            method="dns_txt_check",
            evidence="v=spf1 -all confirmed via Google DNS",
        )
        tracker.record_verification(result)

        task = tracker.get_task("jtmdai-002")
        assert task is not None
        assert task.status == RemediationStatus.VERIFIED_COMPLETE
        assert task.last_checked != ""

    def test_record_verification_fail(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()

        result = VerificationResult(
            task_id="jtmdai-004",
            passed=False,
            method="dmarc_check",
            evidence="p=none found, expected p=reject",
        )
        tracker.record_verification(result)

        task = tracker.get_task("jtmdai-004")
        assert task is not None
        assert task.status == RemediationStatus.IN_PROGRESS

    def test_record_verification_nonexistent_task(self) -> None:
        tracker = SecurityRemediationTracker()
        result = VerificationResult(
            task_id="nonexistent",
            passed=True,
            method="test",
        )
        tracker.record_verification(result)  # Should not raise

    def test_latest_verification(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()

        r1 = VerificationResult(task_id="jtmdai-001", passed=False, method="ssl_check")
        r2 = VerificationResult(task_id="jtmdai-001", passed=True, method="ssl_check")
        tracker.record_verification(r1)
        tracker.record_verification(r2)

        latest = tracker.latest_verification("jtmdai-001")
        assert latest is not None
        assert latest.passed is True

    def test_latest_verification_no_history(self) -> None:
        tracker = SecurityRemediationTracker()
        assert tracker.latest_verification("jtmdai-001") is None


# ---------------------------------------------------------------------------
# Summary stats
# ---------------------------------------------------------------------------

class TestSummaryStats:
    def test_summary_stats_all_not_started(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        stats = tracker.summary_stats()

        assert stats["total_tasks"] == 16
        assert stats["completed"] == 0
        assert stats["remaining"] == 16
        assert stats["completion_pct"] == 0.0
        assert stats["critical_open"] == 1

    def test_summary_stats_after_completion(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()

        result = VerificationResult(
            task_id="jtmdai-001",
            passed=True,
            method="ssl_check",
            evidence="SSL Labs grade A confirmed",
        )
        tracker.record_verification(result)

        stats = tracker.summary_stats()
        assert stats["completed"] == 1
        assert stats["critical_open"] == 0
        assert stats["remaining"] == 15

    def test_summary_stats_empty_tracker(self) -> None:
        tracker = SecurityRemediationTracker()
        stats = tracker.summary_stats()
        assert stats["total_tasks"] == 0
        assert stats["completion_pct"] == 0

    def test_overdue_tasks(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        # All jtmdai tasks have due dates before 2026-03-22
        # Since today is 2026-03-18, tasks due before today are overdue
        overdue = tracker.overdue_tasks()
        # Tasks with due_date before 2026-03-18 are overdue
        for task in overdue:
            assert task.due_date < "2026-03-18"
            assert task.status != RemediationStatus.VERIFIED_COMPLETE


# ---------------------------------------------------------------------------
# Notion sync data
# ---------------------------------------------------------------------------

class TestNotionSyncData:
    def test_notion_sync_data_schema(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        data = tracker.notion_sync_data()

        assert len(data) == 16
        first = data[0]
        # Matches Notion tracker schema
        assert "task_id" in first
        assert "task" in first
        assert "category" in first
        assert "due_date" in first
        assert "last_checked" in first
        assert "notes" in first
        assert "severity" in first
        assert "status" in first
        assert "domain" in first
        assert "owner_agent" in first

    def test_notion_sync_data_sorted_by_severity(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        data = tracker.notion_sync_data()

        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4}
        for i in range(len(data) - 1):
            current = severity_order.get(data[i]["severity"], 5)
            next_sev = severity_order.get(data[i + 1]["severity"], 5)
            assert current <= next_sev


# ---------------------------------------------------------------------------
# CLI summary text
# ---------------------------------------------------------------------------

class TestSummaryText:
    def test_summary_text_includes_header(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        text = tracker.summary_text()
        assert "JTMDAI.COM SECURITY REMEDIATION TRACKER" in text

    def test_summary_text_includes_stats(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        text = tracker.summary_text()
        assert "Total: 16 tasks" in text
        assert "Agent Ownership:" in text

    def test_summary_text_shows_critical_warning(self) -> None:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()
        text = tracker.summary_text()
        assert "CRITICAL" in text


# ---------------------------------------------------------------------------
# Task data model
# ---------------------------------------------------------------------------

class TestRemediationTask:
    def test_auto_assigns_owner_agent(self) -> None:
        task = RemediationTask(
            task_id="test-001",
            title="Test task",
            category=RemediationCategory.EMAIL_SECURITY,
            severity=RemediationSeverity.HIGH,
        )
        assert task.owner_agent == "archivist"

    def test_custom_owner_agent_preserved(self) -> None:
        task = RemediationTask(
            task_id="test-002",
            title="Test task",
            category=RemediationCategory.EMAIL_SECURITY,
            severity=RemediationSeverity.HIGH,
            owner_agent="custom_agent",
        )
        assert task.owner_agent == "custom_agent"

    def test_default_status_is_not_started(self) -> None:
        task = RemediationTask(
            task_id="test-003",
            title="Test task",
            category=RemediationCategory.HTTP_SECURITY,
            severity=RemediationSeverity.MEDIUM,
        )
        assert task.status == RemediationStatus.NOT_STARTED

    def test_default_domain_is_jtmdai(self) -> None:
        task = RemediationTask(
            task_id="test-004",
            title="Test task",
            category=RemediationCategory.HTTP_SECURITY,
            severity=RemediationSeverity.MEDIUM,
        )
        assert task.domain == "jtmdai.com"


# ---------------------------------------------------------------------------
# Category agent mapping
# ---------------------------------------------------------------------------

class TestCategoryAgentMap:
    def test_all_categories_have_agents(self) -> None:
        for cat in RemediationCategory:
            assert cat in CATEGORY_AGENT_MAP

    def test_email_security_owned_by_archivist(self) -> None:
        assert CATEGORY_AGENT_MAP[RemediationCategory.EMAIL_SECURITY] == "archivist"

    def test_cloudflare_config_owned_by_web_architect(self) -> None:
        assert CATEGORY_AGENT_MAP[RemediationCategory.CLOUDFLARE_CONFIG] == "web_architect"

    def test_webflow_owned_by_website_manager(self) -> None:
        assert CATEGORY_AGENT_MAP[RemediationCategory.WEBFLOW_PLATFORM] == "website_manager"

    def test_brand_protection_owned_by_archivist(self) -> None:
        assert CATEGORY_AGENT_MAP[RemediationCategory.BRAND_PROTECTION] == "archivist"
