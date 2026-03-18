"""Security Remediation Tracker — domain-level threat tracking and verification.

Mirrors the Notion "JTMDAI.com Security Remediation Tracker" database schema:
    Task, Category, Due Date, Last Checked, Notes, Severity, Status

Integrates with:
    - WebArchitect: automated security header/SSL verification
    - WebsiteManager: per-site security posture tracking
    - NotionRemediationSync: push verification results to Notion tracker
    - Archivist: DNS history and data sovereignty checks

Categories map to Guardian One agent responsibilities:
    Email Security     → Archivist (domain protection)
    Cloudflare Config  → WebArchitect (infrastructure security)
    Webflow Platform   → WebsiteManager (CMS security)
    HTTP Security      → WebArchitect (header enforcement)
    Infrastructure     → WebArchitect + Archivist (CVE patching)
    Brand Protection   → Archivist (domain/typosquat defense)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RemediationSeverity(Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


class RemediationStatus(Enum):
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    VERIFIED_COMPLETE = "Verified Complete"
    BLOCKED = "Blocked"


class RemediationCategory(Enum):
    EMAIL_SECURITY = "Email Security"
    CLOUDFLARE_CONFIG = "Cloudflare Config"
    WEBFLOW_PLATFORM = "Webflow Platform"
    HTTP_SECURITY = "HTTP Security"
    INFRASTRUCTURE = "Infrastructure"
    BRAND_PROTECTION = "Brand Protection"


# Agent ownership mapping: which Guardian One agent is responsible
CATEGORY_AGENT_MAP: dict[RemediationCategory, str] = {
    RemediationCategory.EMAIL_SECURITY: "archivist",
    RemediationCategory.CLOUDFLARE_CONFIG: "web_architect",
    RemediationCategory.WEBFLOW_PLATFORM: "website_manager",
    RemediationCategory.HTTP_SECURITY: "web_architect",
    RemediationCategory.INFRASTRUCTURE: "web_architect",
    RemediationCategory.BRAND_PROTECTION: "archivist",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class RemediationTask:
    """A single security remediation task matching the Notion tracker schema."""
    task_id: str
    title: str
    category: RemediationCategory
    severity: RemediationSeverity
    status: RemediationStatus = RemediationStatus.NOT_STARTED
    due_date: str = ""
    last_checked: str = ""
    notes: str = ""
    domain: str = "jtmdai.com"
    verification_method: str = ""
    owner_agent: str = ""
    auto_verifiable: bool = False

    def __post_init__(self) -> None:
        if not self.owner_agent:
            self.owner_agent = CATEGORY_AGENT_MAP.get(self.category, "web_architect")


@dataclass
class VerificationResult:
    """Result of an automated verification check on a remediation task."""
    task_id: str
    passed: bool
    method: str
    evidence: str = ""
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Default jtmdai.com remediation tasks (from Notion tracker)
# ---------------------------------------------------------------------------

def _jtmdai_remediation_tasks() -> list[RemediationTask]:
    """Build the full 16-task remediation list from the Notion tracker."""
    return [
        RemediationTask(
            task_id="jtmdai-001",
            title="CRITICAL — Set Cloudflare SSL/TLS mode to Full (Strict)",
            category=RemediationCategory.CLOUDFLARE_CONFIG,
            severity=RemediationSeverity.CRITICAL,
            due_date="2026-03-14",
            notes="Go to Cloudflare Dashboard → SSL/TLS → set to Full (Strict). "
                  "Verify via SSL Labs grade A.",
            verification_method="ssl_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="jtmdai-002",
            title="HIGH — Publish SPF TXT record to prevent email spoofing",
            category=RemediationCategory.EMAIL_SECURITY,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-14",
            notes="In Cloudflare DNS, add TXT record: v=spf1 -all",
            verification_method="dns_txt_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="jtmdai-003",
            title="HIGH — Configure DKIM selector record",
            category=RemediationCategory.EMAIL_SECURITY,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-15",
            notes="If you never plan to send email from this domain, "
                  "a null DKIM record is acceptable.",
            verification_method="dns_txt_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="jtmdai-004",
            title="HIGH — Publish DMARC record at _dmarc.jtmdai.com",
            category=RemediationCategory.EMAIL_SECURITY,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-14",
            notes="In Cloudflare DNS, add TXT record: "
                  "v=DMARC1; p=reject; rua=mailto:...@dmarc-reports.cloudflare.net",
            verification_method="dmarc_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="jtmdai-005",
            title="HIGH — Audit historical DNS records for origin IP exposure",
            category=RemediationCategory.CLOUDFLARE_CONFIG,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-15",
            notes="Check SecurityTrails (securitytrails.com) for historical A records "
                  "that may have exposed the origin server IP.",
            verification_method="dns_history_check",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="jtmdai-006",
            title="MEDIUM-HIGH — Audit Webflow CMS for uploaded files",
            category=RemediationCategory.WEBFLOW_PLATFORM,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-16",
            notes="Files uploaded to Webflow CMS may contain metadata. "
                  "Review all uploads for sensitive data.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="jtmdai-007",
            title="MEDIUM-HIGH — Enable Cloudflare WAF Managed Ruleset",
            category=RemediationCategory.CLOUDFLARE_CONFIG,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-16",
            notes="Cloudflare Free plan only has basic WAF. "
                  "Enable managed ruleset under Security → WAF.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="jtmdai-008",
            title="MEDIUM — Enable TLS 1.3 minimum, disable older versions",
            category=RemediationCategory.CLOUDFLARE_CONFIG,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-19",
            notes="In Cloudflare → SSL/TLS → Edge Certificates → set minimum TLS to 1.3.",
            verification_method="tls_version_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="jtmdai-009",
            title="MEDIUM — Audit all Webflow custom code embeds",
            category=RemediationCategory.WEBFLOW_PLATFORM,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-18",
            notes="Real-world Webflow sites have had XSS via custom code embeds. "
                  "Review all embed blocks.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="jtmdai-010",
            title="MEDIUM — Disable or password-protect Webflow staging URL",
            category=RemediationCategory.WEBFLOW_PLATFORM,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-17",
            notes="Your Webflow staging URL (something.webflow.io) should not be "
                  "publicly accessible.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="jtmdai-011",
            title="MEDIUM — Add security headers via Cloudflare Transform Rules",
            category=RemediationCategory.HTTP_SECURITY,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-17",
            notes="Webflow does not inject security headers natively. "
                  "Use Cloudflare Transform Rules to add CSP, X-Frame-Options, etc.",
            verification_method="header_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="jtmdai-012",
            title="MEDIUM — Configure Content Security Policy (CSP)",
            category=RemediationCategory.HTTP_SECURITY,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-19",
            notes="CSP prevents XSS attacks by whitelisting allowed content sources.",
            verification_method="header_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="jtmdai-013",
            title="MEDIUM — Monitor and patch CVE-2025-68613 (n8n)",
            category=RemediationCategory.INFRASTRUCTURE,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-14",
            notes="VARYS alert: CVE-2025-68613 is active. "
                  "Upgrade n8n at drdaddychaos88.app.n8n.cloud immediately.",
            verification_method="version_check",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="jtmdai-014",
            title="LOW — Register typosquat protection domains",
            category=RemediationCategory.BRAND_PROTECTION,
            severity=RemediationSeverity.LOW,
            due_date="2026-03-20",
            notes="All common typosquat variants should be registered or monitored.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="jtmdai-015",
            title="INFO — Run SecurityHeaders.com and SSL Labs scans",
            category=RemediationCategory.HTTP_SECURITY,
            severity=RemediationSeverity.INFO,
            due_date="2026-03-21",
            notes="Once all header and SSL tasks are done, run final verification "
                  "scans at securityheaders.com and ssllabs.com.",
            verification_method="external_scan",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="jtmdai-016",
            title="INFO — Set up HSTS preload and submit to hstspreload.org",
            category=RemediationCategory.HTTP_SECURITY,
            severity=RemediationSeverity.INFO,
            due_date="2026-03-22",
            notes="After HSTS header is confirmed working, submit to the HSTS "
                  "preload list for browser-level enforcement.",
            verification_method="header_check",
            auto_verifiable=True,
        ),
    ]


# ---------------------------------------------------------------------------
# Remediation Tracker
# ---------------------------------------------------------------------------

class SecurityRemediationTracker:
    """Tracks and verifies security remediation tasks per domain.

    Coordinates with WebArchitect, WebsiteManager, and Archivist agents
    to run automated verification checks where possible.

    Usage:
        tracker = SecurityRemediationTracker()
        tracker.load_defaults()  # Loads 16 jtmdai.com tasks

        # Run automated verification
        results = tracker.verify_all()

        # Get Notion-safe data for sync
        data = tracker.notion_sync_data()
    """

    def __init__(self) -> None:
        self._tasks: dict[str, RemediationTask] = {}
        self._verification_history: dict[str, list[VerificationResult]] = {}

    def load_defaults(self) -> None:
        """Load the default jtmdai.com remediation tasks."""
        for task in _jtmdai_remediation_tasks():
            self._tasks[task.task_id] = task

    def add_task(self, task: RemediationTask) -> None:
        self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> RemediationTask | None:
        return self._tasks.get(task_id)

    def all_tasks(self) -> list[RemediationTask]:
        return list(self._tasks.values())

    def tasks_by_domain(self, domain: str) -> list[RemediationTask]:
        return [t for t in self._tasks.values() if t.domain == domain]

    def tasks_by_category(self, category: RemediationCategory) -> list[RemediationTask]:
        return [t for t in self._tasks.values() if t.category == category]

    def tasks_by_severity(self, severity: RemediationSeverity) -> list[RemediationTask]:
        return [t for t in self._tasks.values() if t.severity == severity]

    def tasks_by_status(self, status: RemediationStatus) -> list[RemediationTask]:
        return [t for t in self._tasks.values() if t.status == status]

    def tasks_by_agent(self, agent_name: str) -> list[RemediationTask]:
        return [t for t in self._tasks.values() if t.owner_agent == agent_name]

    def auto_verifiable_tasks(self) -> list[RemediationTask]:
        return [t for t in self._tasks.values() if t.auto_verifiable]

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def record_verification(self, result: VerificationResult) -> None:
        """Record a verification result and update task status."""
        task = self._tasks.get(result.task_id)
        if not task:
            return

        if result.task_id not in self._verification_history:
            self._verification_history[result.task_id] = []
        self._verification_history[result.task_id].append(result)

        task.last_checked = result.checked_at
        if result.passed:
            task.status = RemediationStatus.VERIFIED_COMPLETE
            task.notes = f"{task.notes} | Verified: {result.evidence}"
        else:
            if task.status == RemediationStatus.NOT_STARTED:
                task.status = RemediationStatus.IN_PROGRESS
            task.notes = f"{task.notes} | Check failed: {result.evidence}"

    def latest_verification(self, task_id: str) -> VerificationResult | None:
        history = self._verification_history.get(task_id, [])
        return history[-1] if history else None

    # ------------------------------------------------------------------
    # Summary / stats
    # ------------------------------------------------------------------

    def summary_stats(self) -> dict[str, Any]:
        """Aggregate stats for the tracker."""
        tasks = list(self._tasks.values())
        total = len(tasks)

        by_status = {}
        for s in RemediationStatus:
            count = sum(1 for t in tasks if t.status == s)
            if count > 0:
                by_status[s.value] = count

        by_severity = {}
        for sev in RemediationSeverity:
            count = sum(1 for t in tasks if t.severity == sev)
            if count > 0:
                by_severity[sev.value] = count

        by_category = {}
        for cat in RemediationCategory:
            count = sum(1 for t in tasks if t.category == cat)
            if count > 0:
                by_category[cat.value] = count

        completed = sum(1 for t in tasks if t.status == RemediationStatus.VERIFIED_COMPLETE)
        critical_open = sum(
            1 for t in tasks
            if t.severity == RemediationSeverity.CRITICAL
            and t.status != RemediationStatus.VERIFIED_COMPLETE
        )

        return {
            "total_tasks": total,
            "completed": completed,
            "remaining": total - completed,
            "completion_pct": round((completed / total) * 100, 1) if total > 0 else 0,
            "critical_open": critical_open,
            "by_status": by_status,
            "by_severity": by_severity,
            "by_category": by_category,
        }

    def overdue_tasks(self) -> list[RemediationTask]:
        """Return tasks past their due date that are not yet complete."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return [
            t for t in self._tasks.values()
            if t.due_date and t.due_date < now
            and t.status != RemediationStatus.VERIFIED_COMPLETE
        ]

    # ------------------------------------------------------------------
    # Notion sync data
    # ------------------------------------------------------------------

    def notion_sync_data(self) -> list[dict[str, Any]]:
        """Return all tasks as Notion-safe dicts matching the tracker schema.

        Schema: Task, Category, Due Date, Last Checked, Notes, Severity, Status
        """
        data = []
        for task in self._tasks.values():
            data.append({
                "task_id": task.task_id,
                "task": task.title,
                "category": task.category.value,
                "due_date": task.due_date,
                "last_checked": task.last_checked,
                "notes": task.notes,
                "severity": task.severity.value,
                "status": task.status.value,
                "domain": task.domain,
                "owner_agent": task.owner_agent,
                "auto_verifiable": task.auto_verifiable,
            })
        return sorted(data, key=lambda d: {
            "Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4,
        }.get(d["severity"], 5))

    def load_domain_defaults(self, domain: str) -> None:
        """Load remediation tasks for a specific domain."""
        if domain == "jtmdai.com":
            for task in _jtmdai_remediation_tasks():
                self._tasks[task.task_id] = task
        elif domain == "drjeremytabernero.org":
            for task in _drjt_remediation_tasks():
                self._tasks[task.task_id] = task

    def load_all_domains(self) -> None:
        """Load remediation tasks for all managed domains."""
        self.load_defaults()
        for task in _drjt_remediation_tasks():
            self._tasks[task.task_id] = task

    def domains(self) -> list[str]:
        """Return all unique domains in the tracker."""
        return list({t.domain for t in self._tasks.values()})

    # ------------------------------------------------------------------
    # CLI display
    # ------------------------------------------------------------------

    def summary_text(self) -> str:
        """Human-readable summary for CLI output."""
        stats = self.summary_stats()
        tasks = self.all_tasks()

        lines = [
            "JTMDAI.COM SECURITY REMEDIATION TRACKER",
            "=" * 60,
            f"Total: {stats['total_tasks']} tasks | "
            f"Complete: {stats['completed']} | "
            f"Remaining: {stats['remaining']} | "
            f"{stats['completion_pct']}% done",
        ]

        if stats["critical_open"] > 0:
            lines.append(f"[!!] {stats['critical_open']} CRITICAL task(s) still open")

        overdue = self.overdue_tasks()
        if overdue:
            lines.append(f"[!!] {len(overdue)} task(s) overdue")

        lines.append("")
        lines.append(f"{'#':<4} {'Sev':<10} {'Category':<20} {'Status':<18} Title")
        lines.append("-" * 90)

        severity_order = {
            RemediationSeverity.CRITICAL: 0,
            RemediationSeverity.HIGH: 1,
            RemediationSeverity.MEDIUM: 2,
            RemediationSeverity.LOW: 3,
            RemediationSeverity.INFO: 4,
        }
        sorted_tasks = sorted(tasks, key=lambda t: severity_order.get(t.severity, 5))

        for i, task in enumerate(sorted_tasks, 1):
            status_icon = {
                RemediationStatus.VERIFIED_COMPLETE: "[OK]",
                RemediationStatus.IN_PROGRESS: "[..]",
                RemediationStatus.BLOCKED: "[!!]",
                RemediationStatus.NOT_STARTED: "[  ]",
            }.get(task.status, "[??]")

            lines.append(
                f"{i:<4} {task.severity.value:<10} "
                f"{task.category.value:<20} "
                f"{status_icon} {task.status.value:<13} "
                f"{task.title}"
            )

        lines.append("")
        lines.append("Agent Ownership:")
        agent_counts: dict[str, int] = {}
        for task in tasks:
            agent_counts[task.owner_agent] = agent_counts.get(task.owner_agent, 0) + 1
        for agent, count in sorted(agent_counts.items()):
            lines.append(f"  {agent}: {count} task(s)")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# drjeremytabernero.org remediation tasks
# ---------------------------------------------------------------------------

def _drjt_remediation_tasks() -> list[RemediationTask]:
    """Remediation tasks for drjeremytabernero.org based on Cloudflare DNS state.

    Current state observed:
        - CNAME root → long-smoke-da3d (Proxied)
        - CNAME www → long-smoke-da3d (Proxied)
        - TXT _dmarc → v=DMARC1; p=none  (NEEDS p=reject)
        - TXT root → v=spf1 -all (OK)
        - Site status: DOWN (needs redeployment)
    """
    return [
        RemediationTask(
            task_id="drjt-001",
            title="HIGH — Upgrade DMARC policy from p=none to p=reject",
            category=RemediationCategory.EMAIL_SECURITY,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-19",
            domain="drjeremytabernero.org",
            notes="Currently p=none (monitoring only). Update _dmarc TXT record to p=reject.",
            verification_method="dmarc_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="drjt-002",
            title="HIGH — Redeploy site (currently DOWN)",
            category=RemediationCategory.INFRASTRUCTURE,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-20",
            domain="drjeremytabernero.org",
            notes="Site is offline per config status: down. CNAME points to long-smoke-da3d. "
                  "Needs redeployment via WebsiteManager.",
            verification_method="uptime_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="drjt-003",
            title="MEDIUM — Add security headers via Cloudflare Transform Rules",
            category=RemediationCategory.HTTP_SECURITY,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-21",
            domain="drjeremytabernero.org",
            notes="Same header set needed as jtmdai.com: CSP, X-Frame-Options, "
                  "Referrer-Policy, Permissions-Policy.",
            verification_method="header_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="drjt-004",
            title="MEDIUM — Configure DKIM selector record",
            category=RemediationCategory.EMAIL_SECURITY,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-21",
            domain="drjeremytabernero.org",
            notes="No DKIM record found. Add null DKIM if no email sending planned.",
            verification_method="dns_txt_check",
            auto_verifiable=True,
        ),
        RemediationTask(
            task_id="drjt-005",
            title="MEDIUM — Enable SSL/TLS Full (Strict) mode",
            category=RemediationCategory.CLOUDFLARE_CONFIG,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-20",
            domain="drjeremytabernero.org",
            notes="Verify Cloudflare SSL/TLS is set to Full (Strict) for this domain.",
            verification_method="ssl_check",
            auto_verifiable=True,
        ),
    ]
