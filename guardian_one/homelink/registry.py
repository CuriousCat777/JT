"""Integration Registry — catalog of all external service connections.

Every API integration includes:
    - Threat model (top 5 risks)
    - Failure model (what happens when the service is down)
    - Rollback procedure
    - Authentication method
    - Data flow description
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ThreatEntry:
    """A single threat in a threat model."""
    risk: str
    severity: str    # low, medium, high, critical
    mitigation: str


@dataclass
class IntegrationRecord:
    """Full registration record for an external service integration."""
    name: str
    description: str
    base_url: str
    auth_method: str         # jwt, api_key, oauth2, basic
    data_flow: str           # Description of data in/out
    vault_keys: list[str] = field(default_factory=list)  # Credential names in vault

    threat_model: list[ThreatEntry] = field(default_factory=list)
    failure_impact: str = ""
    rollback_procedure: str = ""

    registered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    owner_agent: str = ""    # Which agent primarily uses this
    status: str = "active"   # active, disabled, deprecated


# ---------------------------------------------------------------------------
# Pre-built integration records for known services
# ---------------------------------------------------------------------------

DOORDASH_INTEGRATION = IntegrationRecord(
    name="doordash_drive",
    description="DoorDash Drive API v2 — delivery creation and tracking",
    base_url="https://openapi.doordash.com",
    auth_method="jwt",
    data_flow="Agent sends pickup/dropoff details → DoorDash returns delivery status + tracking URL. "
              "No personal financial data transmitted; order value in cents only.",
    vault_keys=["DOORDASH_DEVELOPER_ID", "DOORDASH_KEY_ID", "DOORDASH_SIGNING_SECRET"],
    threat_model=[
        ThreatEntry("Token theft via memory dump", "high",
                    "JWT TTL limited to 5 min; signing secret in encrypted vault only."),
        ThreatEntry("Man-in-the-middle interception", "medium",
                    "TLS 1.3 enforced via gateway; certificate pinning recommended."),
        ThreatEntry("Rate-limit abuse / account lockout", "medium",
                    "Gateway rate limiter set to 60 req/min; circuit breaker at 5 failures."),
        ThreatEntry("Unauthorized delivery creation", "high",
                    "Access restricted to doordash agent via RBAC; all calls audited."),
        ThreatEntry("Credential leak in logs", "high",
                    "Gateway redacts Authorization headers from all audit entries."),
    ],
    failure_impact="Orders fall back to local-only tracking; no deliveries created. "
                   "Jeremy can order manually via DoorDash app.",
    rollback_procedure="1. Disable doordash agent in config YAML. "
                       "2. Revoke JWT credentials at developer.doordash.com. "
                       "3. Rotate signing secret in vault. "
                       "4. Review audit log for unauthorized calls.",
    owner_agent="doordash",
)

ROCKET_MONEY_INTEGRATION = IntegrationRecord(
    name="rocket_money",
    description="Rocket Money — unified financial account aggregation",
    base_url="https://api.rocketmoney.com",
    auth_method="api_key",
    data_flow="Agent requests account balances and transactions → Rocket Money returns "
              "aggregated financial data. Sensitive: account numbers, balances.",
    vault_keys=["ROCKET_MONEY_API_KEY"],
    threat_model=[
        ThreatEntry("API key compromise exposes all financial data", "critical",
                    "Key stored in encrypted vault; 90-day rotation enforced."),
        ThreatEntry("Data exfiltration via compromised agent", "critical",
                    "CFO agent has read-only scope; no transfer/payment capability."),
        ThreatEntry("Stale data leading to incorrect financial decisions", "medium",
                    "Sync timestamps tracked; alerts if data is >24h stale."),
        ThreatEntry("Service outage blocks financial dashboard", "low",
                    "Local cache of last-known balances displayed with staleness warning."),
        ThreatEntry("Man-in-the-middle interception of financial data", "high",
                    "TLS 1.3 enforced; all financial data encrypted at rest."),
    ],
    failure_impact="CFO dashboard shows cached data with staleness indicator. "
                   "No financial actions are blocked.",
    rollback_procedure="1. Disable cfo sync in config. "
                       "2. Revoke API key at rocketmoney.com. "
                       "3. Rotate key in vault. "
                       "4. Clear local cache of financial data.",
    owner_agent="cfo",
)

GOOGLE_CALENDAR_INTEGRATION = IntegrationRecord(
    name="google_calendar",
    description="Google Calendar API — event sync for Chronos",
    base_url="https://www.googleapis.com/calendar/v3",
    auth_method="oauth2",
    data_flow="Chronos reads calendar events and creates reminders. "
              "Write access limited to agent-created events only.",
    vault_keys=["GOOGLE_CALENDAR_CREDENTIALS"],
    threat_model=[
        ThreatEntry("OAuth token theft grants calendar access", "high",
                    "Refresh tokens stored in vault; access tokens short-lived (1h)."),
        ThreatEntry("Unauthorized event creation/deletion", "medium",
                    "Agent scoped to read + create; no delete permission."),
        ThreatEntry("Privacy leak of meeting details in logs", "medium",
                    "Event titles/descriptions redacted from audit log."),
        ThreatEntry("Google API quota exhaustion", "low",
                    "Rate limiter at 100 req/min; caching of recent events."),
        ThreatEntry("Account takeover via compromised credentials", "critical",
                    "OAuth scope restricted to calendar only; 2FA on Google account."),
    ],
    failure_impact="Chronos uses locally cached events; no new events synced.",
    rollback_procedure="1. Revoke OAuth token at myaccount.google.com/permissions. "
                       "2. Delete credentials from vault. "
                       "3. Re-authorize with restricted scope.",
    owner_agent="chronos",
)

GMAIL_INTEGRATION = IntegrationRecord(
    name="gmail_api",
    description="Gmail API — inbox monitoring, email search, attachment download",
    base_url="https://gmail.googleapis.com/gmail/v1",
    auth_method="oauth2",
    data_flow="Agent reads inbox metadata and searches for specific emails (Rocket Money CSVs, "
              "financial alerts). Read-only scope — no sending or deleting.",
    vault_keys=["GMAIL_OAUTH_TOKEN"],
    threat_model=[
        ThreatEntry("OAuth token theft grants inbox read access", "critical",
                    "Refresh tokens in vault; access tokens expire in 1h; scope limited to readonly."),
        ThreatEntry("Sensitive email content exposed in logs", "high",
                    "Only metadata (subject, sender, date) logged; body content never persisted in audit."),
        ThreatEntry("Phishing email processed as legitimate", "medium",
                    "Sender domain validation on financial emails; known-sender allowlist."),
        ThreatEntry("Google API quota exhaustion", "low",
                    "Rate limiter at 50 req/min; caching of recent results."),
        ThreatEntry("Account takeover via compromised OAuth credentials", "critical",
                    "OAuth scope restricted to gmail.readonly; 2FA enforced on Google account."),
    ],
    failure_impact="Gmail monitoring disabled; no inbox alerts. "
                   "Jeremy checks email manually via Gmail app.",
    rollback_procedure="1. Revoke OAuth token at myaccount.google.com/permissions. "
                       "2. Delete token from vault and config/gmail_token.json. "
                       "3. Re-authorize with restricted readonly scope.",
    owner_agent="gmail",
)

N8N_INTEGRATION = IntegrationRecord(
    name="n8n_workflows",
    description="n8n Workflow Automation — website build, deploy, security scan, uptime monitoring",
    base_url="http://localhost:5678",
    auth_method="api_key",
    data_flow="WebArchitect creates and executes workflows → n8n runs automations "
              "(page generation, security header injection, SSL checks, uptime pings). "
              "No sensitive personal data transmitted; domain names and page content only.",
    vault_keys=["N8N_API_KEY"],
    threat_model=[
        ThreatEntry("API key compromise grants full workflow access", "critical",
                    "Key stored in encrypted vault; 90-day rotation enforced; scoped to workflow CRUD."),
        ThreatEntry("Malicious workflow injection via API", "high",
                    "All workflow creation audited; only WebArchitect agent has n8n access via RBAC."),
        ThreatEntry("n8n instance exposed to public internet", "high",
                    "Gateway enforces TLS; n8n should be bound to localhost or VPN only."),
        ThreatEntry("Workflow execution runs arbitrary code", "medium",
                    "Code nodes sandboxed; no filesystem or network access beyond configured integrations."),
        ThreatEntry("Denial of service via excessive workflow executions", "medium",
                    "Rate limiter at 30 req/min; circuit breaker at 5 failures."),
    ],
    failure_impact="Website workflows unavailable; sites remain deployed with last-known state. "
                   "Uptime monitoring paused until n8n reconnects.",
    rollback_procedure="1. Disable web_architect agent in config YAML. "
                       "2. Deactivate all workflows in n8n UI. "
                       "3. Revoke API key in n8n settings. "
                       "4. Rotate key in vault. "
                       "5. Review audit log for unauthorized workflow executions.",
    owner_agent="web_architect",
)

EMPOWER_INTEGRATION = IntegrationRecord(
    name="empower",
    description="Empower (Personal Capital) — retirement account management and investment tracking",
    base_url="https://api.empower.com",
    auth_method="api_key",
    data_flow="CFO reads retirement account balances, holdings, and transaction history. "
              "Read-only — no trading or fund transfer capability.",
    vault_keys=["EMPOWER_API_KEY"],
    threat_model=[
        ThreatEntry("API key compromise exposes retirement account data", "critical",
                    "Key stored in encrypted vault; 90-day rotation enforced; read-only scope."),
        ThreatEntry("Session hijacking via stolen token", "high",
                    "Session tokens short-lived; re-auth required after timeout."),
        ThreatEntry("Investment data exfiltration via compromised agent", "critical",
                    "CFO agent has read-only access; no trade execution or transfer capability."),
        ThreatEntry("Stale portfolio data leading to incorrect planning", "medium",
                    "Sync timestamps tracked; alerts if data is >24h stale."),
        ThreatEntry("Man-in-the-middle interception of financial data", "high",
                    "TLS 1.3 enforced; all financial data encrypted at rest in vault."),
    ],
    failure_impact="Retirement account data unavailable; CFO uses last cached balances. "
                   "No investment actions are blocked.",
    rollback_procedure="1. Revoke API key at empower.com account settings. "
                       "2. Delete credentials from vault. "
                       "3. Rotate key in vault. "
                       "4. Review audit log for unauthorized data access.",
    owner_agent="cfo",
)

NORDVPN_INTEGRATION = IntegrationRecord(
    name="nordvpn",
    description="NordVPN — VPN status monitoring and connection management",
    base_url="local_cli",
    auth_method="api_key",
    data_flow="Archivist queries VPN connection status; no sensitive data transmitted.",
    vault_keys=["NORDVPN_TOKEN"],
    threat_model=[
        ThreatEntry("VPN token compromise allows account takeover", "high",
                    "Token in vault; rotation every 90 days."),
        ThreatEntry("Kill switch failure leaks real IP", "high",
                    "Archivist monitors kill switch status; alerts on misconfiguration."),
        ThreatEntry("DNS leak despite VPN connection", "medium",
                    "NordLynx protocol enforced; DNS leak tests scheduled."),
        ThreatEntry("VPN down without detection", "medium",
                    "Connection status checked every 15 minutes."),
        ThreatEntry("API rate limiting on status checks", "low",
                    "CLI-based; no external API rate limits."),
    ],
    failure_impact="VPN status unknown; Archivist flags as unmonitored.",
    rollback_procedure="1. Disconnect VPN manually. "
                       "2. Revoke token at nordaccount.com. "
                       "3. Re-authenticate via NordVPN CLI.",
    owner_agent="archivist",
)


class IntegrationRegistry:
    """Catalog of all registered external service integrations."""

    def __init__(self) -> None:
        self._integrations: dict[str, IntegrationRecord] = {}

    def register(self, record: IntegrationRecord) -> None:
        self._integrations[record.name] = record

    def get(self, name: str) -> IntegrationRecord | None:
        return self._integrations.get(name)

    def list_all(self) -> list[str]:
        return list(self._integrations.keys())

    def by_agent(self, agent: str) -> list[IntegrationRecord]:
        return [r for r in self._integrations.values() if r.owner_agent == agent]

    def active(self) -> list[IntegrationRecord]:
        return [r for r in self._integrations.values() if r.status == "active"]

    def threat_summary(self) -> list[dict[str, Any]]:
        """Aggregate all threats across integrations."""
        threats = []
        for record in self._integrations.values():
            for t in record.threat_model:
                threats.append({
                    "service": record.name,
                    "risk": t.risk,
                    "severity": t.severity,
                    "mitigation": t.mitigation,
                })
        return sorted(threats, key=lambda t: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(t["severity"], 4))

    def load_defaults(self) -> None:
        """Register all known integrations."""
        for record in [
            DOORDASH_INTEGRATION,
            ROCKET_MONEY_INTEGRATION,
            EMPOWER_INTEGRATION,
            GOOGLE_CALENDAR_INTEGRATION,
            GMAIL_INTEGRATION,
            NORDVPN_INTEGRATION,
            N8N_INTEGRATION,
        ]:
            self.register(record)
