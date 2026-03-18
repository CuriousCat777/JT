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
    CONNECTOR_SECURITY = "Connector Security"


# Agent ownership mapping: which Guardian One agent is responsible
CATEGORY_AGENT_MAP: dict[RemediationCategory, str] = {
    RemediationCategory.EMAIL_SECURITY: "archivist",
    RemediationCategory.CLOUDFLARE_CONFIG: "web_architect",
    RemediationCategory.WEBFLOW_PLATFORM: "website_manager",
    RemediationCategory.HTTP_SECURITY: "web_architect",
    RemediationCategory.INFRASTRUCTURE: "web_architect",
    RemediationCategory.BRAND_PROTECTION: "archivist",
    RemediationCategory.CONNECTOR_SECURITY: "archivist",
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
            notes="AUDIT FINDINGS (2026-03-18):\n"
                  "  jtmdai.com current A: 104.21.68.33, 172.67.185.218 (Cloudflare)\n"
                  "  jtmdai.com current AAAA: 2606:4700:3030::ac43:b9da, 2606:4700:3035::6815:4421 (Cloudflare)\n"
                  "  drjeremytabernero.org current A: 104.26.6.33, 104.26.7.33, 172.67.69.100 (Cloudflare)\n"
                  "  drjeremytabernero.org current AAAA: 2606:4700:20::681a:621, 2606:4700:20::681a:721, 2606:4700:20::ac43:4564 (Cloudflare)\n"
                  "  MX records: NONE for either domain (GOOD — no origin leak via MX)\n"
                  "  Subdomains checked (mail, ftp, direct, staging, api): NONE resolve (GOOD)\n"
                  "  Root CNAME: not set (A records used, proxied via Cloudflare)\n"
                  "  All IPs are in Cloudflare ranges (104.x, 172.67.x, 2606:4700:x) — no origin exposure.\n"
                  "  REMAINING: Check SecurityTrails, ViewDNS.info, Censys manually for HISTORICAL A records\n"
                  "  that may have existed BEFORE Cloudflare was enabled. These services require\n"
                  "  authenticated browser access.\n"
                  "  CHECK: https://securitytrails.com/domain/jtmdai.com/dns\n"
                  "  CHECK: https://securitytrails.com/domain/drjeremytabernero.org/dns\n"
                  "  CHECK: https://viewdns.info/iphistory/?domain=jtmdai.com\n"
                  "  CHECK: https://viewdns.info/iphistory/?domain=drjeremytabernero.org\n"
                  "  CHECK: https://search.censys.io/hosts?q=jtmdai.com\n"
                  "  CHECK: https://search.censys.io/hosts?q=drjeremytabernero.org",
            verification_method="dns_history_check",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="jtmdai-006",
            title="CRITICAL — Audit Webflow CMS for uploaded files (CDN exposure risk)",
            category=RemediationCategory.WEBFLOW_PLATFORM,
            severity=RemediationSeverity.CRITICAL,
            due_date="2026-03-18",
            notes="CRITICAL FINDING: Files uploaded to Webflow CMS are PUBLICLY accessible\n"
                  "via CDN URL even if the page is password-protected. Deleted files PERSIST\n"
                  "on the CDN until Webflow Support manually removes them.\n"
                  "ACTION REQUIRED:\n"
                  "  1. Audit ALL files uploaded to Webflow CMS for both domains\n"
                  "  2. Verify NO PHI, PII, credentials, contracts, or financial documents exist\n"
                  "  3. If sensitive files found: contact Webflow Support for CDN purge\n"
                  "  4. Add content classification gate to WebsiteManager upload pipeline\n"
                  "  5. NEVER upload sensitive documents to Webflow CMS — use Vault instead\n"
                  "DOMAINS: jtmdai.com, drjeremytabernero.org (if Webflow-hosted)",
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
            title="HIGH — TLS hardening: minimum TLS 1.2+, enable 1.3, force HTTPS",
            category=RemediationCategory.CLOUDFLARE_CONFIG,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-19",
            notes="Full TLS hardening checklist for jtmdai.com:\n"
                  "  1. Cloudflare → SSL/TLS → Edge Certificates → Minimum TLS Version: TLS 1.2 (minimum)\n"
                  "  2. Enable TLS 1.3 toggle\n"
                  "  3. Enable Automatic HTTPS Rewrites\n"
                  "  4. Enable Always Use HTTPS\n"
                  "  5. Run SSL Labs test: ssllabs.com/ssltest/analyze.html?d=jtmdai.com\n"
                  "  6. Target grade: A or higher\n"
                  "  7. Repeat for drjeremytabernero.org",
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

    def load_connector_tasks(self) -> None:
        """Load connector/MCP security remediation tasks."""
        for task in _connector_remediation_tasks():
            self._tasks[task.task_id] = task

    def load_all_domains(self) -> None:
        """Load remediation tasks for all managed domains + connectors."""
        self.load_defaults()
        for task in _drjt_remediation_tasks():
            self._tasks[task.task_id] = task
        self.load_connector_tasks()

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


# ---------------------------------------------------------------------------
# Connector security remediation tasks
# Addresses Claude Desktop/MCP connector attack surface
# ---------------------------------------------------------------------------

def _connector_remediation_tasks() -> list[RemediationTask]:
    """Remediation tasks for Claude connector/MCP attack surface.

    Based on audit of active connectors in Claude Desktop:
        Web: 19 connectors (7 needed, 12 unnecessary attack surface)
        Desktop: 10 connectors (3 DANGEROUS, 4 unused)
    """
    return [
        RemediationTask(
            task_id="conn-001",
            title="CRITICAL — Disconnect Desktop Commander MCP when not in active use",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.CRITICAL,
            due_date="2026-03-18",
            domain="system",
            notes="Desktop Commander grants unrestricted shell execution. "
                  "Can read .env, vault files, kill processes, exfiltrate data. "
                  "ONLY enable during active supervised development.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="conn-002",
            title="CRITICAL — Disconnect Windows-MCP when not in active use",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.CRITICAL,
            due_date="2026-03-18",
            domain="system",
            notes="Windows-MCP grants PowerShell execution, registry access, "
                  "service management. Can disable Defender, access Credential Manager. "
                  "ONLY enable during active supervised admin tasks.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="conn-003",
            title="HIGH — Scope AWS API MCP to read-only IAM policy",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-19",
            domain="system",
            notes="AWS MCP with broad IAM permissions can create resources, "
                  "incur costs, access S3 data. Restrict to read-only. "
                  "Set billing alerts at $10/$50/$100.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="conn-004",
            title="HIGH — Scope Filesystem MCP to project directories only",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-19",
            domain="system",
            notes="Filesystem MCP should NOT have access to home directory root, "
                  "/etc, or any directory containing credentials. "
                  "Restrict to ~/JT and specific project paths.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="conn-005",
            title="HIGH — Disconnect 12 unused web connectors",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-20",
            domain="system",
            notes="Disconnect: AWS Marketplace, bioRxiv, Canva, Clinical Trials, "
                  "CMS Coverage, Common Room, Consensus, Kiwi.com, Lumin, "
                  "NPI Registry, Spotify, Weather. "
                  "Each unused connector is attack surface maintained for free.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="conn-006",
            title="HIGH — Audit Zapier connected services and active Zaps",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.HIGH,
            due_date="2026-03-20",
            domain="system",
            notes="Zapier account compromise cascades to ALL connected services. "
                  "Audit active Zaps, disable unused ones, enable 2FA, "
                  "review OAuth scopes granted to each connection.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="conn-007",
            title="MEDIUM — Enable 2FA on all connected service accounts",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-22",
            domain="system",
            notes="Verify 2FA is enabled on: GitHub, Google (Gmail/Calendar/Drive), "
                  "Cloudflare, Webflow, Notion, Zapier, n8n cloud, AWS.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="conn-008",
            title="MEDIUM — Review GitHub PAT/OAuth token scopes",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-21",
            domain="system",
            notes="GitHub token should have minimum required scopes. "
                  "No admin:org, no delete_repo. Review at github.com/settings/tokens.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="conn-009",
            title="MEDIUM — Restrict Google Drive OAuth scope to specific folders",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.MEDIUM,
            due_date="2026-03-22",
            domain="system",
            notes="Google Drive OAuth should use drive.file or folder-scoped access, "
                  "NOT drive (full access). Re-authorize with restricted scope.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
        RemediationTask(
            task_id="conn-010",
            title="INFO — Document all active connectors and their justification",
            category=RemediationCategory.CONNECTOR_SECURITY,
            severity=RemediationSeverity.INFO,
            due_date="2026-03-25",
            domain="system",
            notes="Create a connector inventory: name, purpose, OAuth scopes, "
                  "owner agent, last used date. Disconnect anything unused for 30+ days.",
            verification_method="manual_review",
            auto_verifiable=False,
        ),
    ]
