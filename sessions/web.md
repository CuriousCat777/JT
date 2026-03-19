# Session Handoff: Web Architect + Website Manager (Web Properties)

> Last updated: 2026-03-19
> Branch: `claude/guardian-one-system-4uvJv`

---

## What This Session Covers

You are working on **Guardian One's web infrastructure** — two complementary components:
- **WebArchitect** (Agent): n8n workflow orchestration, security enforcement, uptime monitoring
- **WebsiteManager** (Utility): Per-site build/deploy pipelines, page inventory, Notion dashboards

---

## Managed Websites

| Domain | Label | Type | Status | Pages |
|--------|-------|------|--------|-------|
| **drjeremytabernero.org** | Dr. Jeremy Tabernero | Professional | **DOWN** | index, about, contact, cv, publications |
| **jtmdai.com** | JTMD AI | Business | **LIVE** | index, about, services, contact, case-studies |

---

## Files You Own

| File | Lines | Purpose |
|------|-------|---------|
| `guardian_one/agents/web_architect.py` | 422 | n8n workflows, security scans, uptime, deployments |
| `guardian_one/agents/website_manager.py` | 307 | Per-site build/deploy pipelines, page inventory |
| `guardian_one/integrations/n8n_sync.py` | 451 | n8n REST API, JWT auth, workflow templates |
| `guardian_one/integrations/notion_website_sync.py` | 351 | Notion dashboard sync (write-only, content-gated) |
| `tests/test_web_architect.py` | 472 | 72 tests |
| `tests/test_website_manager.py` | 265 | 24 tests |
| `tests/test_notion_website_sync.py` | 194 | 8 tests |

---

## Data Structures

```python
# WebArchitect
@dataclass
class SiteSecurityReport:
    domain: str
    headers_present: list[str]
    headers_missing: list[str]
    ssl_valid: bool
    ssl_expiry: str
    passed: bool
    scanned_at: str

@dataclass
class UptimeRecord:
    domain: str
    up: bool
    status_code: int
    response_time_ms: float
    checked_at: str

# WebsiteManager
@dataclass
class SitePage:
    filename: str                    # "index.html"
    title: str                       # "Home"
    template: str                    # unused currently
    last_built: str
    status: str                      # pending | built | deployed | error

@dataclass
class SiteBuild:
    build_id: str
    domain: str
    pages_built: int
    started_at: str
    finished_at: str
    status: str                      # running | success | failed
    errors: list[str]

@dataclass
class ManagedSite:
    domain: str
    label: str
    site_type: str                   # professional | business
    pages: list[SitePage]
    features: list[str]
    hosting: str
    builds: list[SiteBuild]
    deployed: bool
    last_deployed: str
    ssl_enabled: bool
    security_passed: bool
    notion_page_id: str
    notion_dashboard: bool

# n8n
@dataclass
class N8nWorkflow:
    id: str
    name: str
    active: bool
    tags: list[str]
    nodes: list[dict]
    created_at: str
    updated_at: str
    raw: dict

@dataclass
class N8nExecution:
    id: str
    workflow_id: str
    status: str                      # success | error | waiting | running
    started_at: str
    finished_at: str
    mode: str
    data: dict
    raw: dict

@dataclass
class WebsiteDeployment:
    domain: str
    workflow_id: str
    status: str
    deployed_at: str
    ssl_enabled: bool
    pages: list[str]
    security_scan_passed: bool
```

---

## Method Reference

### WebArchitect (Agent)
```python
# Site Management
wa.create_site(domain) -> WebsiteDeployment   # Creates 3 n8n workflows
wa.deploy_site(domain) -> N8nExecution | None  # Execute build workflow
wa.list_domains() -> list[str]
wa.get_deployment(domain) -> WebsiteDeployment | None
wa.domain_status(domain) -> dict               # Full status

# Security
wa.security_policy() -> dict                   # Enforced headers
wa.get_security_report(domain) -> SiteSecurityReport | None

# Uptime
wa.record_uptime(domain, up, status_code, response_time_ms)
wa.uptime_summary(domain, last_n=100) -> dict  # pct_uptime, avg_response_time

# Workflows
wa.list_workflows() -> dict[str, N8nWorkflow]
```

### WebsiteManager (Utility)
```python
wm.initialize()
wm.list_sites() -> list[str]
wm.get_site(domain) -> ManagedSite | None
wm.build_site(domain) -> SiteBuild
wm.build_all() -> dict[str, SiteBuild]
wm.deploy_site(domain) -> dict                 # Requires successful prior build
wm.deploy_all() -> dict[str, dict]
wm.site_status(domain) -> dict
wm.all_sites_status() -> dict[str, dict]
wm.site_dashboard_data(domain) -> dict         # Notion-safe (no sensitive data)
wm.summary() -> str                            # Human-readable multi-line
```

### N8nAPIProvider
```python
n8n = N8nAPIProvider(base_url=None, api_key=None)
n8n.authenticate() -> bool
n8n.list_workflows() -> list[N8nWorkflow]
n8n.get_workflow(workflow_id) -> N8nWorkflow | None
n8n.create_workflow(name, nodes) -> N8nWorkflow | None
n8n.activate_workflow(workflow_id) -> bool
n8n.deactivate_workflow(workflow_id) -> bool
n8n.execute_workflow(workflow_id, data=None) -> N8nExecution | None
n8n.get_execution(execution_id) -> N8nExecution | None
```

### NotionWebsiteDashboard
```python
dash = NotionWebsiteDashboard(notion_sync, audit)
dash.push_site_dashboard(site_data: dict) -> SyncResult
dash.push_sites_overview(sites_data: dict) -> SyncResult
dash.sync_all(sites_data: dict) -> dict[str, SyncResult]
```

---

## Security Policy (Enforced Headers)

**Required (scan fails without):**
- `Content-Security-Policy: default-src 'self'`
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`

**Default (recommended):**
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`

---

## n8n Workflow Templates

**Per-site, 3 workflows created:**

1. **Build workflow** (5 nodes): Trigger → Generate Pages → Security Headers → SSL Check → Deploy
2. **Security scan** (3 nodes): Trigger → Header Scan → Analyze
3. **Uptime monitor** (3 nodes): Schedule (5-min) → Health Check → Evaluate

---

## What's Working vs Stubbed

| Feature | Status |
|---------|--------|
| Site creation with 3 n8n workflows | Working (online + offline) |
| n8n API CRUD (workflows, executions) | Working |
| Security header validation | Working (checks present/missing) |
| Uptime tracking + summary | Working |
| Domain status aggregation | Working |
| Build pipeline (state tracking) | Working |
| Deploy pipeline (state tracking) | Working |
| Notion dashboard sync (per-site + overview) | Working |
| Content classification gate | Working |
| **Actual security HTTP HEAD scans** | **Stub** |
| **Actual uptime HTTP checks** | **Stub** (n8n scheduled) |
| **Real page generation/compilation** | **Stub** |
| **Real deploy upload** | **Stub** |

---

## Development Tracks

### Track 1: Bring drjeremytabernero.org Back Online (URGENT)
- Config shows status: `down`
- Build → deploy → verify security headers
- Wire up real n8n execution

### Track 2: Real Security Scans
- Implement actual HTTP HEAD requests in `_run_security_check()`
- Check SSL certificate expiry with real cert validation
- Vulnerability scanning beyond headers

### Track 3: Real Build/Deploy Pipeline
- Integrate static site generator (11ty, Hugo, or custom)
- WebsiteManager.build_site() → actually generates HTML
- WebsiteManager.deploy_site() → actually uploads to VPS

### Track 4: n8n Connection Hardening
- Retry/circuit breaker for API failures
- Webhook handler for execution callbacks
- Execution polling for long-running workflows

### Track 5: Uptime Alerting
- Wire uptime monitor results back from n8n
- Alert on SLA breaches (<99% uptime)
- Integrate with notifications system

### Track 6: Cost Tracking
- Hosting costs → CFO agent
- Build/deploy duration metrics
- Per-site resource usage

---

## CLI Commands

```bash
python main.py --websites              # All site status
python main.py --website-build all     # Build all sites
python main.py --website-build drjeremytabernero.org  # Build one
python main.py --website-deploy all    # Deploy all
python main.py --website-sync          # Push dashboards to Notion
python main.py --security-review       # Security remediation tracking
python main.py --security-sync         # Push security dashboard to Notion
```

---

## Config (guardian_config.yaml)

```yaml
agents:
  web_architect:
    enabled: true
    schedule_interval_minutes: 30
    allowed_resources: [n8n_workflows, deployments, security_scans, uptime_records]
    custom:
      domains: [drjeremytabernero.org, jtmdai.com]
      enforce_security_headers: true
      ssl_required: true
      uptime_check_interval_minutes: 5
      coordinate_with_archivist: true
      coordinate_with_cfo: true
      sites:
        drjeremytabernero.org:
          label: "Dr. Jeremy Tabernero — Personal & Professional"
          site_type: professional
          status: down
          pages: [index.html, about.html, contact.html, cv.html, publications.html]
          features: [contact_form, cv_download, publications_list]
        jtmdai.com:
          label: "JTMD AI — AI Solutions & Technology"
          site_type: business
          status: live
          pages: [index.html, about.html, services.html, contact.html, case-studies.html]
          features: [service_catalog, case_studies, contact_form, ai_demos]
```

**Env vars:** `N8N_BASE_URL`, `N8N_API_KEY`

---

## Test Coverage

| Suite | Tests | Coverage |
|-------|-------|---------|
| WebArchitect | 72 | Init, create, deploy, security, uptime, run, templates, registry |
| WebsiteManager | 24 | Init, build, deploy, status, helpers |
| Notion Website Sync | 8 | Dashboard push, overview, sync all, content gate |
| **Total** | **104** | |

---

## Cross-Agent Integration

| Agent | Integration | Direction |
|-------|-------------|-----------|
| **CFO** | Hosting costs | WebArchitect → CFO |
| **Archivist** | Site backups, asset storage | WebArchitect → Archivist |
| **DeviceAgent** | Home status on jtmdai.com | DeviceAgent → WebArchitect |
| **Chronos** | Maintenance window scheduling | Chronos → WebArchitect |
| **Notion** | Per-site dashboards (write-only) | WebsiteManager → Notion |
