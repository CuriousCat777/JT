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
    additional_agents: list[str] = field(default_factory=list)  # Extra agents allowed
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

PLAID_INTEGRATION = IntegrationRecord(
    name="plaid",
    description="Plaid — Direct read-only bank connections (BofA, Wells Fargo, Capital One, etc.)",
    base_url="https://production.plaid.com",
    auth_method="api_key",
    data_flow="CFO reads account balances and transaction history via Plaid Link. "
              "Strictly read-only — no transfers, payments, or account modifications.",
    vault_keys=["PLAID_CLIENT_ID", "PLAID_SECRET"],
    threat_model=[
        ThreatEntry("Plaid credentials compromise exposes all linked bank data", "critical",
                    "Credentials in encrypted vault; 90-day rotation; read-only products only."),
        ThreatEntry("Access token theft grants bank account read access", "critical",
                    "Tokens stored encrypted; each institution has a separate token; revocable via /item/remove."),
        ThreatEntry("Man-in-the-middle interception of bank data", "high",
                    "TLS 1.3 enforced; Plaid handles bank-to-Plaid encryption; _request() validates endpoints."),
        ThreatEntry("Unauthorized write operations via compromised agent", "high",
                    "PlaidProvider._READ_ONLY_ENDPOINTS whitelist blocks all non-read endpoints; "
                    "ALLOWED_PRODUCTS never includes transfer or payment_initiation."),
        ThreatEntry("Stale data from failed bank sync", "medium",
                    "Sync timestamps tracked per institution; alerts if data is >24h stale."),
    ],
    failure_impact="Bank account data unavailable; CFO uses last cached balances from ledger. "
                   "No financial actions are blocked.",
    rollback_procedure="1. Run 'python main.py --connect' and disconnect individual banks. "
                       "2. Delete data/plaid_tokens.json. "
                       "3. Revoke access at dashboard.plaid.com. "
                       "4. Rotate credentials in vault.",
    owner_agent="cfo",
)

NOTION_INTEGRATION = IntegrationRecord(
    name="notion",
    description="Notion API — write-only workspace sync for operational dashboards",
    base_url="https://api.notion.com",
    auth_method="api_key",
    data_flow="Guardian pushes agent status, roadmap progress, integration health, "
              "and deliverable tracking to Notion.  Strictly write-only — Guardian "
              "never reads Notion content for decision-making.  Content classification "
              "gate blocks PHI/PII/credentials from leaving the system.",
    vault_keys=["NOTION_TOKEN"],
    threat_model=[
        ThreatEntry("Token exfiltration grants workspace write access", "critical",
                    "Token stored in encrypted Vault (PBKDF2+Fernet); loaded on-demand, "
                    "never cached as attribute; auth headers redacted from audit log."),
        ThreatEntry("PHI/PII accidentally synced to Notion cloud", "critical",
                    "Content classification gate with regex pattern matching blocks SSN, "
                    "MRN, credit cards, bank accounts, emails.  Only allow-listed categories sync."),
        ThreatEntry("Notion used as C2 channel (attacker writes commands)", "high",
                    "Write-only architecture: Guardian pushes to Notion but never reads "
                    "content for execution.  No eval/exec/shell of Notion-sourced data."),
        ThreatEntry("Rate limit exhaustion causes sync failures", "medium",
                    "350ms minimum between requests; Retry-After header respected; "
                    "Gateway circuit breaker at 5 failures; batch writes (100 blocks/call)."),
        ThreatEntry("Notion outage blocks operational visibility", "low",
                    "Graceful degradation — Guardian operates independently; "
                    "Notion is a read-only mirror, not a control plane."),
    ],
    failure_impact="Notion workspace shows stale data.  Guardian One continues "
                   "operating normally — Notion is observability only, not control.",
    rollback_procedure="1. Remove NOTION_TOKEN from Vault. "
                       "2. Disable notion sync in config YAML. "
                       "3. Revoke integration at notion.so/my-integrations. "
                       "4. Review audit log for unauthorized sync operations.",
    owner_agent="notion_sync",
    additional_agents=["notion_website_sync"],
)

CLOUDFLARE_INTEGRATION = IntegrationRecord(
    name="cloudflare",
    description="Cloudflare — DNS, SSL/TLS, WAF, Workers, Transform Rules for managed domains",
    base_url="https://api.cloudflare.com/client/v4",
    auth_method="api_key",
    data_flow="WebArchitect monitors DNS records, SSL/TLS settings, security headers, "
              "and WAF status.  Read-only for verification; configuration changes "
              "made manually via Cloudflare dashboard.",
    vault_keys=["CLOUDFLARE_API_TOKEN"],
    threat_model=[
        ThreatEntry("API token compromise grants DNS/WAF control", "critical",
                    "Token scoped to read-only zones; stored in encrypted vault; 90-day rotation."),
        ThreatEntry("Origin IP exposed via historical DNS records", "high",
                    "All A/CNAME records proxied through Cloudflare; audit via SecurityTrails."),
        ThreatEntry("DMARC/SPF misconfiguration allows email spoofing", "high",
                    "Automated DNS TXT verification; p=reject enforced on all domains."),
        ThreatEntry("Cloudflare Workers execute malicious code", "medium",
                    "Workers managed via dashboard only; no programmatic deployment without audit."),
        ThreatEntry("SSL/TLS downgrade attack via misconfigured mode", "high",
                    "Full (Strict) mode enforced; automated SSL Labs grade verification."),
    ],
    failure_impact="DNS and CDN remain functional; verification scans fail gracefully. "
                   "Security posture unknown until Cloudflare API reconnects.",
    rollback_procedure="1. Revoke API token at dash.cloudflare.com. "
                       "2. Remove token from vault. "
                       "3. DNS continues to function without API access. "
                       "4. Review audit log for unauthorized changes.",
    owner_agent="web_architect",
    additional_agents=["archivist"],
)

WEBFLOW_INTEGRATION = IntegrationRecord(
    name="webflow",
    description="Webflow — CMS platform hosting jtmdai.com",
    base_url="https://api.webflow.com",
    auth_method="api_key",
    data_flow="WebsiteManager reads site metadata and CMS content for security auditing. "
              "Builds and deploys managed through Webflow dashboard and Cloudflare Workers.",
    vault_keys=["WEBFLOW_API_TOKEN"],
    threat_model=[
        ThreatEntry("CMS files publicly accessible via CDN even if page is password-protected", "critical",
                    "NEVER upload PHI, PII, credentials, contracts, or financial docs to Webflow CMS. "
                    "All CMS uploads are publicly accessible via CDN URL regardless of page protection. "
                    "Deleted files PERSIST on CDN until Webflow Support manually purges them. "
                    "Content classification gate must block sensitive uploads."),
        ThreatEntry("CMS upload contains malicious files or metadata", "medium",
                    "All uploaded files audited by Archivist; metadata stripped on deploy."),
        ThreatEntry("Custom code embed introduces XSS vulnerability", "high",
                    "Custom code embeds reviewed quarterly; CSP headers block inline scripts."),
        ThreatEntry("Staging URL exposes pre-release content", "medium",
                    "Staging URL password-protected; not indexed by search engines."),
        ThreatEntry("API token compromise grants CMS write access", "high",
                    "Token stored in vault; scoped to read-only where possible."),
        ThreatEntry("Webflow platform outage takes down live site", "medium",
                    "Cloudflare cache serves stale content; Workers provide fallback."),
    ],
    failure_impact="Site remains live via Cloudflare cache. CMS editing unavailable "
                   "until Webflow recovers.",
    rollback_procedure="1. Revoke API token in Webflow dashboard. "
                       "2. Remove token from vault. "
                       "3. Site continues serving cached content. "
                       "4. Redeploy from local build if needed.",
    owner_agent="website_manager",
    additional_agents=["web_architect"],
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

# ---------------------------------------------------------------------------
# IoT / Smart Home integrations
# ---------------------------------------------------------------------------

TPLINK_KASA_INTEGRATION = IntegrationRecord(
    name="tplink_kasa",
    description="TP-Link Kasa/Tapo — smart plugs and switches via local LAN API",
    base_url="local_lan",
    auth_method="api_key",
    data_flow="DeviceAgent discovers TP-Link devices via UDP broadcast on LAN. "
              "Controls power state, schedules, and energy monitoring via python-kasa. "
              "All communication stays on local network — no cloud dependency required.",
    vault_keys=["TPLINK_CLOUD_USER", "TPLINK_CLOUD_PASS"],
    threat_model=[
        ThreatEntry("Unencrypted LAN commands allow replay attacks", "high",
                    "TP-Link local protocol uses XOR obfuscation, not encryption. "
                    "Mitigate: isolate on IoT VLAN; block internet access at router."),
        ThreatEntry("Cloud account compromise grants remote device control", "high",
                    "Use local-only mode where possible; disable cloud features in app; "
                    "enable 2FA on TP-Link account; unique password in Vault."),
        ThreatEntry("Firmware vulnerability enables device takeover", "high",
                    "Monitor CVE feeds for TP-Link Kasa/Tapo models; auto-update enabled; "
                    "replace if vendor drops support."),
        ThreatEntry("Device used as network pivot to reach trusted LAN", "medium",
                    "IoT VLAN isolation prevents lateral movement; firewall rules "
                    "block IoT-to-trusted traffic."),
        ThreatEntry("Energy monitoring data reveals occupancy patterns", "medium",
                    "Data stays local; no cloud sync of usage patterns; "
                    "energy data treated as PII by content classification gate."),
    ],
    failure_impact="Smart plugs remain in last state. Manual control via physical button. "
                   "No safety risk — plugs fail-safe to last state.",
    rollback_procedure="1. Reset plug to factory via physical button (hold 5s). "
                       "2. Remove from TP-Link cloud account. "
                       "3. Re-pair with local-only configuration.",
    owner_agent="device_agent",
)

PHILIPS_HUE_INTEGRATION = IntegrationRecord(
    name="philips_hue",
    description="Philips Hue — smart lighting via Zigbee through Hue Bridge local API",
    base_url="local_lan",
    auth_method="api_key",
    data_flow="DeviceAgent communicates with Hue Bridge over local HTTPS API (port 443). "
              "Bridge controls all Hue bulbs/strips via Zigbee. API key obtained by "
              "physical button press on bridge. No cloud required for local control.",
    vault_keys=["HUE_BRIDGE_API_KEY"],
    threat_model=[
        ThreatEntry("Bridge API key theft grants full lighting control", "medium",
                    "API key in Vault; requires physical button press to generate; "
                    "revoke via bridge factory reset if compromised."),
        ThreatEntry("Zigbee protocol vulnerabilities (ZigBee Light Link)", "high",
                    "Hue Bridge firmware addresses known Zigbee vulnerabilities. "
                    "Keep firmware updated. Zigbee range limited to ~30m."),
        ThreatEntry("Bridge firmware vulnerability enables network pivot", "high",
                    "Bridge on IoT VLAN; firmware auto-update enabled; "
                    "Philips has strong security track record (Signify)."),
        ThreatEntry("Cloud account enables remote access if connected", "medium",
                    "Disable Hue cloud/remote access if not needed; use local-only; "
                    "enable 2FA on Hue account if cloud features used."),
        ThreatEntry("Lighting patterns reveal occupancy to outside observers", "low",
                    "Schedule randomization available; away-mode varies patterns; "
                    "not a high risk for apartment/house with curtains."),
    ],
    failure_impact="Lights remain in last state. Physical switches still work. "
                   "Bridge reboot restores full control.",
    rollback_procedure="1. Factory reset Hue Bridge (pin hole button, hold 5s). "
                       "2. Re-pair bulbs (power cycle 5x). "
                       "3. Generate new API key via physical button press. "
                       "4. Store new key in Vault.",
    owner_agent="device_agent",
)

GOVEE_INTEGRATION = IntegrationRecord(
    name="govee",
    description="Govee — smart LED lights/strips via LAN UDP API or cloud REST API",
    base_url="https://developer-api.govee.com",
    auth_method="api_key",
    data_flow="DeviceAgent controls Govee devices via local LAN UDP broadcast (newer models) "
              "or Govee cloud API (older models). LAN mode preferred for latency and privacy.",
    vault_keys=["GOVEE_API_KEY"],
    threat_model=[
        ThreatEntry("Cloud API key grants control of all Govee devices", "medium",
                    "API key in Vault; rate limited by Govee (100 req/min); "
                    "use local LAN API where supported to avoid cloud dependency."),
        ThreatEntry("Unencrypted UDP broadcast on LAN", "medium",
                    "LAN UDP commands are not encrypted; isolate on IoT VLAN; "
                    "acceptable risk for lighting control."),
        ThreatEntry("Cloud account compromise", "medium",
                    "Enable 2FA on Govee account; unique password; "
                    "disable cloud features if only using local LAN API."),
        ThreatEntry("BLE pairing allows nearby unauthorized control", "low",
                    "BLE range limited to ~10m; pairing required; "
                    "acceptable for indoor use."),
        ThreatEntry("Firmware update mechanism not verified", "medium",
                    "Govee OTA updates over WiFi; verify firmware versions periodically; "
                    "replace device if vendor drops support."),
    ],
    failure_impact="Lights remain in last state. Govee app provides backup control. "
                   "Physical power switch always works.",
    rollback_procedure="1. Revoke API key at developer.govee.com. "
                       "2. Remove key from Vault. "
                       "3. Factory reset device (varies by model). "
                       "4. Re-pair via Govee app.",
    owner_agent="device_agent",
)

SECURITY_CAMERA_INTEGRATION = IntegrationRecord(
    name="security_cameras",
    description="Security cameras — RTSP/ONVIF local streams with optional NVR",
    base_url="local_lan",
    auth_method="basic",
    data_flow="DeviceAgent monitors camera health and streams via RTSP/ONVIF. "
              "Video stored on local NVR or NAS — never cloud unless explicitly configured. "
              "Motion detection alerts routed through Guardian One notifications.",
    vault_keys=["CAMERA_ADMIN_USER", "CAMERA_ADMIN_PASS"],
    threat_model=[
        ThreatEntry("Default credentials exposed to internet (Shodan/Censys)", "critical",
                    "CHANGE DEFAULT PASSWORD IMMEDIATELY. Use unique credentials per camera. "
                    "Store in Vault. NEVER expose RTSP port to internet."),
        ThreatEntry("Unencrypted RTSP stream intercepted on LAN", "high",
                    "Use RTMPS or RTSP over TLS where supported; isolate cameras on IoT VLAN; "
                    "accept risk if VLAN-isolated and no sensitive areas recorded."),
        ThreatEntry("Camera firmware vulnerability enables RCE", "critical",
                    "Keep firmware updated; subscribe to CVE alerts for camera model; "
                    "block camera internet access at router (local NVR only); "
                    "replace camera if vendor drops security patches."),
        ThreatEntry("Cloud-dependent cameras stream video to vendor servers", "high",
                    "Prefer cameras with local RTSP/ONVIF support; disable cloud features; "
                    "block camera internet access at router if not needed."),
        ThreatEntry("Physical tampering or camera repositioning", "medium",
                    "Mount cameras at height; use tamper-detection alerts if supported; "
                    "pair with motion detectors for redundancy."),
    ],
    failure_impact="Camera offline — no recording for affected area. Motion detectors "
                   "provide backup alerts. NVR continues recording other cameras.",
    rollback_procedure="1. Factory reset camera (usually pinhole button). "
                       "2. Change admin password immediately. "
                       "3. Store new credentials in Vault. "
                       "4. Re-add to NVR/recording system. "
                       "5. Verify RTSP stream is not internet-accessible.",
    owner_agent="device_agent",
)

VEHICLE_INTEGRATION = IntegrationRecord(
    name="vehicle_telematics",
    description="Connected vehicle — OBD-II diagnostics and manufacturer API",
    base_url="local_obd2",
    auth_method="api_key",
    data_flow="OBD-II dongle provides local diagnostic data (engine codes, fuel, battery). "
              "Manufacturer app/API provides remote features (lock, start, GPS). "
              "GPS and location data is PII — classified and never synced externally.",
    vault_keys=["VEHICLE_API_KEY", "VEHICLE_ACCOUNT_PASS"],
    threat_model=[
        ThreatEntry("Manufacturer API compromise enables remote vehicle control", "critical",
                    "Enable 2FA on manufacturer account; unique password in Vault; "
                    "disable remote start if not needed; review API data sharing policy."),
        ThreatEntry("OBD-II dongle as attack vector for CAN bus injection", "high",
                    "Use read-only OBD-II adapters (ELM327); never leave dongle plugged in "
                    "when not in use; disable Bluetooth on dongle when not actively reading."),
        ThreatEntry("GPS/location data reveals home address and daily patterns", "high",
                    "Location data classified as PII; never synced to external services; "
                    "review manufacturer data sharing and opt out where possible."),
        ThreatEntry("Relay attack enables keyless entry theft", "high",
                    "Use Faraday pouch for key fob when at home; disable passive entry "
                    "if supported; Flipper Zero can test for relay vulnerabilities."),
        ThreatEntry("Vehicle API sells telemetry to insurance/data brokers", "medium",
                    "Review manufacturer privacy policy; opt out of data sharing; "
                    "consider aftermarket OBD-II only (no manufacturer cloud)."),
    ],
    failure_impact="Vehicle functions normally without API. Remote features unavailable. "
                   "OBD-II dongle provides independent diagnostics.",
    rollback_procedure="1. Revoke API access at manufacturer portal. "
                       "2. Remove credentials from Vault. "
                       "3. Disconnect OBD-II dongle. "
                       "4. Change account password.",
    owner_agent="device_agent",
)

RYSE_SMARTSHADE_INTEGRATION = IntegrationRecord(
    name="ryse_smartshade",
    description="Ryse SmartShade — motorized window blinds via BLE/WiFi SmartBridge",
    base_url="local_lan",
    auth_method="api_key",
    data_flow="DeviceAgent controls Ryse SmartShade motors via SmartBridge local API. "
              "BLE for direct pairing, WiFi via bridge for automation. "
              "Open/close/position commands from Chronos schedule events. "
              "Cloud API available but local preferred.",
    vault_keys=["RYSE_API_KEY"],
    threat_model=[
        ThreatEntry("BLE pairing allows nearby unauthorized blind control", "medium",
                    "BLE range ~10m; requires initial pairing via Ryse app; "
                    "acceptable for indoor residential use."),
        ThreatEntry("SmartBridge cloud API exposes blind state/schedule", "medium",
                    "Use local API via SmartBridge on IoT VLAN; disable cloud if not needed; "
                    "blind position data is low-sensitivity."),
        ThreatEntry("Firmware vulnerability in SmartBridge", "medium",
                    "Keep SmartBridge firmware updated via Ryse app; "
                    "isolate on IoT VLAN to prevent lateral movement."),
        ThreatEntry("Blind schedule reveals occupancy patterns", "low",
                    "Schedule randomization available; pair with light automations "
                    "to simulate occupancy when away."),
        ThreatEntry("Motor failure leaves blinds in last position", "low",
                    "Manual override always available via physical chain/cord. "
                    "No safety risk — blinds fail-safe to last position."),
    ],
    failure_impact="Blinds remain in last position. Manual cord/chain control always works. "
                   "SmartBridge reboot typically restores connectivity.",
    rollback_procedure="1. Factory reset SmartBridge via pinhole button. "
                       "2. Re-pair motors via Ryse app. "
                       "3. Store new API key in Vault. "
                       "4. Re-configure automation rules.",
    owner_agent="device_agent",
)

FLIPPER_ZERO_INTEGRATION = IntegrationRecord(
    name="flipper_zero",
    description="Flipper Zero — multi-protocol security research tool (sub-GHz, NFC, IR, BLE)",
    base_url="local_usb",
    auth_method="api_key",
    data_flow="USB serial connection only. No network connectivity (unless WiFi dev board). "
              "Used for authorized security testing of owned IoT devices: sub-GHz signal "
              "analysis, NFC badge cloning, IR remote learning, BLE device testing.",
    vault_keys=[],
    threat_model=[
        ThreatEntry("Unauthorized sub-GHz transmission violates FCC regulations", "high",
                    "Only transmit on frequencies legal in your jurisdiction. "
                    "Use for RECEIVE/ANALYZE only unless testing owned devices. "
                    "Sub-GHz TX is region-locked in official firmware."),
        ThreatEntry("Captured NFC/RFID data from access badges stored insecurely", "high",
                    "Captured badge data is sensitive — store on Flipper only for authorized testing. "
                    "Delete captures after testing. Never clone badges you don't own."),
        ThreatEntry("Custom/third-party firmware introduces vulnerabilities", "medium",
                    "Use official Flipper firmware or well-audited alternatives. "
                    "Verify firmware checksums. Keep updated via qFlipper."),
        ThreatEntry("Physical theft of Flipper exposes captured signals", "medium",
                    "Enable PIN lock on Flipper Zero. Regularly purge captured data. "
                    "Treat Flipper as a security-sensitive device."),
        ThreatEntry("WiFi dev board adds network attack surface", "medium",
                    "If WiFi dev board attached: isolate on guest network; "
                    "disable when not actively testing; Marauder firmware for "
                    "authorized WiFi security auditing only."),
    ],
    failure_impact="No impact on home automation. Security testing capabilities unavailable.",
    rollback_procedure="1. Factory reset Flipper via Settings → Storage → Factory Reset. "
                       "2. Reflash official firmware via qFlipper. "
                       "3. Delete all saved captures.",
    owner_agent="device_agent",
)

SMART_TV_INTEGRATION = IntegrationRecord(
    name="smart_tv",
    description="Smart TV — LAN API control with telemetry blocking",
    base_url="local_lan",
    auth_method="api_key",
    data_flow="DeviceAgent communicates with TV via LAN API (Samsung SmartThings / LG ThinQ / Roku). "
              "ACR (Automatic Content Recognition) disabled. Telemetry domains blocked at router.",
    vault_keys=["TV_API_TOKEN"],
    threat_model=[
        ThreatEntry("ACR tracks viewing habits and sells data to advertisers", "high",
                    "DISABLE ACR in TV settings immediately. Block TV telemetry domains "
                    "at router/Pi-hole: samsungacr.com, lgtvsdp.com, etc."),
        ThreatEntry("TV microphone/camera enables surveillance", "high",
                    "Disable voice assistant; cover camera if present; "
                    "block TV internet access except for streaming apps."),
        ThreatEntry("Smart TV firmware vulnerability", "medium",
                    "Keep firmware updated; subscribe to CVE alerts for TV model; "
                    "isolate on IoT VLAN."),
        ThreatEntry("Streaming app credentials stored on TV", "medium",
                    "Use unique passwords for streaming accounts; enable 2FA; "
                    "factory reset TV before selling/disposing."),
        ThreatEntry("UPnP/DLNA on TV exposes media server to network", "medium",
                    "Disable UPnP on TV and router; IoT VLAN isolation prevents "
                    "access to trusted LAN media."),
    ],
    failure_impact="TV functions normally for broadcast/HDMI. Smart features unavailable. "
                   "Use streaming device (Roku/Fire Stick) as backup.",
    rollback_procedure="1. Factory reset TV via settings menu. "
                       "2. Re-disable ACR and voice features. "
                       "3. Re-block telemetry domains at router. "
                       "4. Re-isolate on IoT VLAN.",
    owner_agent="device_agent",
)


NETWORK_INFRA_INTEGRATION = IntegrationRecord(
    name="network_infrastructure",
    description="Home network infrastructure — Spectrum SAX2V1S router, ES2251 modem, TP-Link switch",
    base_url="local_lan",
    auth_method="api_key",
    data_flow="Router admin panel for config. All IoT traffic routes through this gateway. "
              "DNS queries go to Spectrum DNS (no local control — Pi-hole needed). "
              "Modem in default mode (consider bridge mode for NAT control).",
    vault_keys=["ROUTER_ADMIN_PASSWORD"],
    threat_model=[
        ThreatEntry("Spectrum DNS provides zero telemetry blocking capability", "high",
                    "Deploy Pi-hole (Raspberry Pi) or NextDNS as upstream DNS resolver. "
                    "This is the #1 action item for IoT privacy — without it, all "
                    "smart devices phone home freely."),
        ThreatEntry("No VLAN support on Spectrum SAX2V1S limits IoT isolation", "high",
                    "Spectrum gateway does not support VLANs. Options: "
                    "1) Replace with Ubiquiti Dream Machine / pfSense / OPNsense. "
                    "2) Use Spectrum gateway as AP-only, dedicated router for VLAN. "
                    "3) MAC-based filtering as stopgap (weak but better than nothing)."),
        ThreatEntry("Remote management may be enabled by Spectrum by default", "high",
                    "Check router admin for remote management settings. Disable if enabled. "
                    "Spectrum retains ability to push firmware updates — consider replacing."),
        ThreatEntry("ISP-provided router receives uncontrolled firmware updates", "medium",
                    "Spectrum can push firmware to SAX2V1S at any time. Updates could "
                    "re-enable UPnP or change security settings. Monitor after each update."),
        ThreatEntry("TP-Link unmanaged switch has no traffic monitoring or segmentation", "medium",
                    "Upgrade to managed switch (e.g., TP-Link TL-SG108E) for "
                    "port mirroring, VLAN tagging, and traffic monitoring."),
    ],
    failure_impact="Total network outage. All IoT devices, Ring security, and internet access lost. "
                   "Flipper Zero and BLE devices continue functioning.",
    rollback_procedure="1. Factory reset router via physical reset button. "
                       "2. Reconfigure WiFi SSID/password. "
                       "3. Re-disable UPnP. "
                       "4. Verify Security Shield is ON. "
                       "5. Reconnect all IoT devices.",
    owner_agent="device_agent",
)

RING_ALARM_INTEGRATION = IntegrationRecord(
    name="ring_alarm",
    description="Ring Alarm — cloud-only security system (Amazon). "
                "Doorbells, contact sensors, motion detectors, alarm base station.",
    base_url="cloud_only",
    auth_method="oauth2",
    data_flow="ALL Ring data routes through Amazon cloud — video streams, sensor "
              "events, alarm state changes. Zero local API. Ring app communicates "
              "via Amazon servers even on the same LAN. Base station uses Z-Wave "
              "for sensor mesh, then uploads everything to cloud.",
    vault_keys=[],
    threat_model=[
        ThreatEntry("All video and sensor data stored on Amazon servers", "critical",
                    "Ring has no local storage or local API. Every doorbell frame and "
                    "sensor event goes through Amazon. Mitigation: plan migration to "
                    "Frigate NVR + RTSP cameras for local-only security."),
        ThreatEntry("Amazon employees and law enforcement can access video without warrant", "critical",
                    "Ring has shared video with law enforcement. Mitigation: enable "
                    "end-to-end encryption in Ring app (Settings > Video Encryption). "
                    "Long-term: replace with self-hosted solution."),
        ThreatEntry("Ring account compromise exposes all cameras and alarm system", "high",
                    "Enable 2FA on Amazon/Ring account. Use unique strong password. "
                    "Monitor Ring app for unauthorized shared users."),
        ThreatEntry("Z-Wave sensor signals may be interceptable within range", "medium",
                    "Ring uses Z-Wave S2 encryption for sensor communication. "
                    "Verify via Flipper Zero Z-Wave audit that S2 is active."),
        ThreatEntry("Ring cloud outage disables entire security system", "high",
                    "Amazon outages have historically disabled Ring doorbells and alarms. "
                    "No local fallback exists. Supplementary local cameras recommended."),
    ],
    failure_impact="Total security system failure. All doorbells, sensors, and alarm "
                   "monitoring go offline during Amazon/Ring cloud outage. No local fallback.",
    rollback_procedure="1. Ring cannot be 'rolled back' — it's cloud-only. "
                       "2. If compromised: change Amazon password, revoke shared users, "
                       "   enable E2E encryption, review Authorized Client Devices. "
                       "3. Long-term: deploy Frigate NVR + RTSP cameras for local security.",
    owner_agent="device_agent",
)

OLLAMA_INTEGRATION = IntegrationRecord(
    name="ollama",
    description="Ollama — local sovereign LLM inference engine (primary AI backend)",
    base_url="http://localhost:11434",
    auth_method="api_key",
    data_flow="All agent reasoning requests go through local Ollama. "
              "Prompts and responses stay entirely on-device — zero data leaves the machine. "
              "API key authenticates local requests (optional for localhost).",
    vault_keys=["OLLAMA_API_KEY"],
    threat_model=[
        ThreatEntry("Exposed Ollama port allows unauthorized model access", "high",
                    "Bind Ollama to localhost only (default); firewall blocks 11434 from LAN. "
                    "API key required for non-localhost access."),
        ThreatEntry("Prompt injection via compromised agent input", "medium",
                    "System prompts are hardcoded per agent; user input sanitized; "
                    "no eval/exec of model output."),
        ThreatEntry("Model poisoning via malicious model pull", "medium",
                    "Only pull models from official Ollama registry; verify model checksums; "
                    "audit all pull operations."),
        ThreatEntry("Disk exhaustion from large model downloads", "medium",
                    "Monitor disk usage in health checks; alert when >80% full; "
                    "document model sizes before pulling."),
        ThreatEntry("Local model produces biased or incorrect financial advice", "medium",
                    "All financial recommendations flagged for human review; "
                    "CFO agent cross-validates with external data; "
                    "Anthropic fallback available for critical decisions."),
    ],
    failure_impact="AI reasoning falls back to Anthropic Claude API (cloud). "
                   "If both unavailable, agents run in deterministic mode without AI.",
    rollback_procedure="1. Stop Ollama: ollama stop / systemctl stop ollama. "
                       "2. Remove API key from vault. "
                       "3. Switch primary_provider to 'anthropic' in config. "
                       "4. Restart Guardian One.",
    owner_agent="guardian_one",
    additional_agents=["chronos", "cfo", "archivist", "gmail_agent", "web_architect", "doordash"],
)

GITHUB_INTEGRATION = IntegrationRecord(
    name="github",
    description="GitHub — source code repository, CI/CD, issue tracking for Guardian One",
    base_url="https://api.github.com",
    auth_method="oauth2",
    data_flow="Claude Code pushes commits, creates PRs, and manages issues. "
              "Full read/write access to repository contents, branches, and workflows.",
    vault_keys=["GITHUB_TOKEN"],
    threat_model=[
        ThreatEntry("PAT/OAuth token theft grants full repo access", "critical",
                    "Token stored in vault; scoped to minimal required permissions; "
                    "90-day rotation enforced; audit log tracks all pushes."),
        ThreatEntry("Malicious code injection via compromised push", "critical",
                    "Branch protection rules enforced; code scanning enabled; "
                    "signed commits recommended; PR review required for main."),
        ThreatEntry("Secrets accidentally committed to repository", "critical",
                    ".gitignore blocks .env, credentials, tokens; pre-commit hook "
                    "scans for secrets; GitHub secret scanning enabled."),
        ThreatEntry("Webhook secret compromise enables event injection", "high",
                    "Webhook secrets in vault; payload signatures verified; "
                    "webhook URLs not publicly listed."),
        ThreatEntry("CI/CD pipeline manipulation via workflow modification", "high",
                    "Workflow files require PR approval; no self-hosted runners "
                    "without network isolation; GITHUB_TOKEN scoped per-job."),
    ],
    failure_impact="Code push/PR operations unavailable. Local development continues. "
                   "CI/CD pipelines paused until GitHub reconnects.",
    rollback_procedure="1. Revoke token at github.com/settings/tokens. "
                       "2. Delete token from vault. "
                       "3. Rotate any secrets that may have been exposed. "
                       "4. Review recent commits and PR activity for unauthorized changes. "
                       "5. Enable branch protection if not already set.",
    owner_agent="archivist",
    additional_agents=["web_architect"],
)

ZAPIER_INTEGRATION = IntegrationRecord(
    name="zapier",
    description="Zapier — cross-service workflow automation bridge",
    base_url="https://zapier.com",
    auth_method="api_key",
    data_flow="Triggers and actions across connected services. Acts as a bridge "
              "between services that lack direct API integration. Can read/write "
              "data across any connected service in the Zap chain.",
    vault_keys=["ZAPIER_API_KEY"],
    threat_model=[
        ThreatEntry("Zapier account compromise cascades to all connected services", "critical",
                    "Zapier connects to multiple services — a single compromise exposes all. "
                    "Use dedicated Zapier account; enable 2FA; limit connected services to essential."),
        ThreatEntry("Zap chain data leakage across service boundaries", "high",
                    "Data flowing through Zaps may cross trust boundaries unexpectedly. "
                    "Audit all active Zaps quarterly; disable unused Zaps; no PHI/PII in Zap data."),
        ThreatEntry("Third-party Zap app accesses data beyond intended scope", "high",
                    "Only use Zapier-built or verified integrations; review OAuth scopes "
                    "granted to each connection; revoke unnecessary permissions."),
        ThreatEntry("Zapier outage breaks cross-service automation", "medium",
                    "Critical workflows should not depend solely on Zapier; "
                    "Guardian One agents provide fallback for essential operations."),
        ThreatEntry("Webhook URL exposure enables unauthorized trigger injection", "medium",
                    "Webhook URLs treated as secrets; not logged or stored in plaintext; "
                    "IP filtering where supported."),
    ],
    failure_impact="Cross-service automations paused. Guardian One agents continue "
                   "independently. Manual intervention needed for Zap-dependent workflows.",
    rollback_procedure="1. Disable all Zaps at zapier.com. "
                       "2. Revoke API key. "
                       "3. Disconnect all service connections in Zapier. "
                       "4. Review Zap execution history for unauthorized actions. "
                       "5. Re-evaluate which automations are truly needed.",
    owner_agent="archivist",
)

GOOGLE_DRIVE_INTEGRATION = IntegrationRecord(
    name="google_drive",
    description="Google Drive — file storage and document management",
    base_url="https://www.googleapis.com/drive/v3",
    auth_method="oauth2",
    data_flow="Archivist may access files for backup/sovereignty tracking. "
              "Read access to documents; write access limited to Guardian-managed folders.",
    vault_keys=["GOOGLE_DRIVE_CREDENTIALS"],
    threat_model=[
        ThreatEntry("OAuth token theft grants access to all Drive files", "critical",
                    "Token in vault; scope restricted to specific folders only; "
                    "short-lived access tokens (1h); 2FA on Google account."),
        ThreatEntry("Sensitive documents exfiltrated via compromised agent", "high",
                    "Archivist has read-only access; no share/export permissions; "
                    "content classification gate blocks PHI/PII from leaving system."),
        ThreatEntry("Shared Drive links expose documents to unintended audience", "high",
                    "Archivist audits sharing settings; flags publicly shared files; "
                    "alerts on permission changes."),
        ThreatEntry("Google account compromise exposes all cloud data", "critical",
                    "2FA enforced; Google Advanced Protection recommended; "
                    "OAuth scope restricted to drive.readonly."),
        ThreatEntry("Sync conflicts corrupt or overwrite important files", "medium",
                    "Guardian One is read-only for Drive; no write conflicts possible."),
    ],
    failure_impact="Drive file monitoring unavailable. No data loss — Drive continues "
                   "independently. Archivist sovereignty checks paused.",
    rollback_procedure="1. Revoke OAuth token at myaccount.google.com/permissions. "
                       "2. Delete credentials from vault. "
                       "3. Re-authorize with restricted readonly scope if needed.",
    owner_agent="archivist",
)

# ---------------------------------------------------------------------------
# Dangerous Claude Desktop Connectors — tracked for risk awareness
# These are NOT Guardian One integrations but represent additional attack
# surface through the Claude Desktop/MCP ecosystem that should be monitored.
# ---------------------------------------------------------------------------

DESKTOP_COMMANDER_CONNECTOR = IntegrationRecord(
    name="desktop_commander_mcp",
    description="Desktop Commander MCP — DANGEROUS: grants Claude shell execution on local machine",
    base_url="local_mcp",
    auth_method="api_key",
    data_flow="Allows Claude to execute arbitrary shell commands, read/write files, "
              "manage processes on the local machine. Full system access.",
    vault_keys=[],
    threat_model=[
        ThreatEntry("Arbitrary command execution on host machine", "critical",
                    "DISCONNECT IF NOT ACTIVELY NEEDED. Any prompt injection or "
                    "misuse gives full shell access. No sandboxing."),
        ThreatEntry("File system access bypasses all Guardian One content gates", "critical",
                    "Desktop Commander can read .env, vault files, credentials directly. "
                    "Completely bypasses Vault encryption and access control."),
        ThreatEntry("Process killing can disable security monitoring", "high",
                    "Can kill Guardian One agents, VPN, firewall processes. "
                    "No audit trail outside of Claude conversation history."),
        ThreatEntry("Data exfiltration via shell commands (curl, scp, etc.)", "critical",
                    "Shell access means any data on disk can be sent anywhere. "
                    "ONLY enable during active supervised development sessions."),
        ThreatEntry("Privilege escalation if user has sudo access", "critical",
                    "If the user account has sudo, Desktop Commander effectively "
                    "has root access to the entire machine."),
    ],
    failure_impact="No impact if disconnected — this is the recommended state.",
    rollback_procedure="1. DISCONNECT immediately in Claude Desktop settings. "
                       "2. Review recent Claude conversation history for unexpected commands. "
                       "3. Audit file system for unauthorized changes. "
                       "4. Check running processes for anything suspicious.",
    owner_agent="archivist",
    status="active",  # Should be flagged for review
)

FILESYSTEM_MCP_CONNECTOR = IntegrationRecord(
    name="filesystem_mcp",
    description="Filesystem MCP — grants Claude direct file read/write access",
    base_url="local_mcp",
    auth_method="api_key",
    data_flow="Allows Claude to read and write files on the local filesystem. "
              "Scope depends on MCP configuration (may be limited to specific directories).",
    vault_keys=[],
    threat_model=[
        ThreatEntry("Read access to sensitive files (.env, vault, SSH keys)", "critical",
                    "Restrict MCP filesystem scope to project directory only. "
                    "Never grant access to home directory root or /etc."),
        ThreatEntry("Write access can modify code, config, or credentials", "high",
                    "Limit to specific directories; use read-only mode where possible; "
                    "git tracks all file changes for audit."),
        ThreatEntry("Prompt injection could trigger unauthorized file operations", "high",
                    "MCP permission prompts should be enabled; never auto-approve writes."),
        ThreatEntry("Symlink following can escape directory restrictions", "medium",
                    "Ensure MCP respects symlink boundaries; audit symlinks in project."),
        ThreatEntry("Large file reads can exfiltrate data via conversation context", "medium",
                    "Conversation history may contain file contents; "
                    "never read binary files or credential stores."),
    ],
    failure_impact="File operations unavailable via Claude. Manual editing continues normally.",
    rollback_procedure="1. Disconnect in Claude Desktop settings. "
                       "2. Review recent file modifications via git diff. "
                       "3. Restore any unauthorized changes from git history.",
    owner_agent="archivist",
    status="active",
)

AWS_MCP_CONNECTOR = IntegrationRecord(
    name="aws_api_mcp",
    description="AWS API MCP Server — grants Claude access to AWS services",
    base_url="local_mcp",
    auth_method="api_key",
    data_flow="Allows Claude to make AWS API calls. Scope depends on the IAM "
              "credentials configured — could range from read-only to full admin.",
    vault_keys=["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    threat_model=[
        ThreatEntry("AWS credential exposure grants cloud resource control", "critical",
                    "Use IAM roles with minimum required permissions; never use root credentials; "
                    "enable CloudTrail logging; set billing alerts."),
        ThreatEntry("Unintended resource creation incurs costs", "high",
                    "Budget alerts configured; IAM policy restricts resource creation; "
                    "MCP permission prompts enabled for write operations."),
        ThreatEntry("S3 bucket access may expose sensitive data", "high",
                    "IAM policy should restrict to specific buckets; "
                    "bucket policies enforce encryption and access logging."),
        ThreatEntry("Lambda/EC2 creation could be used for crypto mining", "high",
                    "Service quotas set; IAM denies compute resource creation "
                    "unless explicitly needed; billing alerts at $10/$50/$100."),
        ThreatEntry("Credential rotation gap leaves stale access", "medium",
                    "90-day key rotation; unused keys disabled after 30 days; "
                    "IAM Access Analyzer monitors unused permissions."),
    ],
    failure_impact="AWS operations unavailable via Claude. Console/CLI access unaffected.",
    rollback_procedure="1. Deactivate AWS access keys in IAM console. "
                       "2. Remove credentials from local config. "
                       "3. Review CloudTrail for unauthorized API calls. "
                       "4. Check billing dashboard for unexpected charges.",
    owner_agent="archivist",
    status="active",
)

WINDOWS_MCP_CONNECTOR = IntegrationRecord(
    name="windows_mcp",
    description="Windows MCP — DANGEROUS: grants Claude OS-level operations on Windows",
    base_url="local_mcp",
    auth_method="api_key",
    data_flow="Allows Claude to perform Windows-specific operations: registry edits, "
              "service management, PowerShell execution.",
    vault_keys=[],
    threat_model=[
        ThreatEntry("PowerShell execution grants arbitrary code execution", "critical",
                    "DISCONNECT IF NOT ACTIVELY NEEDED. Same risk profile as "
                    "Desktop Commander but Windows-specific."),
        ThreatEntry("Registry modification can disable security features", "critical",
                    "Can disable Windows Defender, firewall, UAC. "
                    "Only enable during supervised admin tasks."),
        ThreatEntry("Service management can stop security monitoring", "high",
                    "Can stop/start Windows services including antivirus, VPN, logging."),
        ThreatEntry("Credential access via Windows Credential Manager", "critical",
                    "PowerShell can query stored credentials, browser passwords, "
                    "Wi-Fi passwords. Major data exfiltration risk."),
        ThreatEntry("System modification persists beyond Claude session", "high",
                    "Registry changes, scheduled tasks, and service modifications "
                    "survive reboot. Harder to detect and roll back."),
    ],
    failure_impact="No impact if disconnected — this is the recommended state.",
    rollback_procedure="1. DISCONNECT immediately in Claude Desktop settings. "
                       "2. Run Windows security scan. "
                       "3. Review Event Viewer for unauthorized changes. "
                       "4. Check scheduled tasks for anything unexpected. "
                       "5. Review registry changes (if System Restore is enabled).",
    owner_agent="archivist",
    status="active",
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
            OLLAMA_INTEGRATION,
            DOORDASH_INTEGRATION,
            ROCKET_MONEY_INTEGRATION,
            EMPOWER_INTEGRATION,
            PLAID_INTEGRATION,
            GOOGLE_CALENDAR_INTEGRATION,
            GMAIL_INTEGRATION,
            NORDVPN_INTEGRATION,
            N8N_INTEGRATION,
            NOTION_INTEGRATION,
            CLOUDFLARE_INTEGRATION,
            WEBFLOW_INTEGRATION,
            GITHUB_INTEGRATION,
            ZAPIER_INTEGRATION,
            GOOGLE_DRIVE_INTEGRATION,
            TPLINK_KASA_INTEGRATION,
            PHILIPS_HUE_INTEGRATION,
            GOVEE_INTEGRATION,
            SECURITY_CAMERA_INTEGRATION,
            VEHICLE_INTEGRATION,
            RYSE_SMARTSHADE_INTEGRATION,
            FLIPPER_ZERO_INTEGRATION,
            SMART_TV_INTEGRATION,
            NETWORK_INFRA_INTEGRATION,
            RING_ALARM_INTEGRATION,
            DESKTOP_COMMANDER_CONNECTOR,
            FILESYSTEM_MCP_CONNECTOR,
            AWS_MCP_CONNECTOR,
            WINDOWS_MCP_CONNECTOR,
        ]:
            self.register(record)

    def dangerous_connectors(self) -> list[IntegrationRecord]:
        """Return connectors flagged as dangerous (should be disconnected when idle)."""
        dangerous_names = {
            "desktop_commander_mcp", "windows_mcp", "aws_api_mcp",
        }
        return [r for r in self._integrations.values() if r.name in dangerous_names]

    def connector_audit(self) -> dict[str, Any]:
        """Audit all registered integrations and connectors.

        Returns a report showing:
            - Critical risk connectors that should be disconnected
            - Integrations missing from the registry
            - Threat model coverage stats
        """
        all_records = list(self._integrations.values())
        critical_threats = [
            {"service": r.name, "threats": [t for t in r.threat_model if t.severity == "critical"]}
            for r in all_records
            if any(t.severity == "critical" for t in r.threat_model)
        ]

        dangerous = self.dangerous_connectors()
        guardian_integrations = [r for r in all_records if not r.name.endswith("_mcp")]
        mcp_connectors = [r for r in all_records if r.name.endswith("_mcp")]

        # Known Claude connectors from the user's setup that SHOULD be tracked
        known_connectors = {
            "aws_marketplace", "biorxiv", "canva", "clinical_trials",
            "cloudflare_dev", "cms_coverage", "common_room", "consensus",
            "github", "gmail", "google_calendar", "google_drive",
            "kiwi_com", "lumin", "n8n", "notion", "npi_registry",
            "webflow", "zapier",
            # Desktop
            "aws_api_mcp", "claude_in_chrome", "desktop_commander_mcp",
            "figma", "filesystem_mcp", "pdf_anthropic", "pdf_tools",
            "spotify", "weather", "windows_mcp",
        }
        tracked = set(self._integrations.keys())
        untracked = known_connectors - tracked

        return {
            "total_registered": len(all_records),
            "guardian_integrations": len(guardian_integrations),
            "mcp_connectors": len(mcp_connectors),
            "dangerous_connectors": [r.name for r in dangerous],
            "critical_threat_services": [
                {"service": c["service"], "count": len(c["threats"])}
                for c in critical_threats
            ],
            "total_threats_modeled": sum(len(r.threat_model) for r in all_records),
            "untracked_connectors": sorted(untracked),
            "recommendation": (
                "DISCONNECT desktop_commander_mcp and windows_mcp when not in active "
                "supervised development. These grant unrestricted system access."
                if dangerous else "No dangerous connectors registered."
            ),
        }
