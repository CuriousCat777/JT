# Guardian One — Claude Code Project Context

## What This Is

Guardian One is a **multi-agent AI orchestration platform** for personal life management,
built for Jeremy Paulo Salvino Tabernero. It coordinates autonomous agents that handle
finance, scheduling, email, meals, websites, smart home devices, and data sovereignty —
all with encryption, audit trails, and zero data exploitation.

## Owner

Jeremy Paulo Salvino Tabernero
Timezone: America/Chicago

## Architecture

```
main.py                              # CLI entry point (~1200 lines, 35+ commands)
mcp_server.py                        # MCP server — exposes Guardian One as MCP tools
guardian_one/
├── agents/                          # Subordinate agents
│   ├── chronos.py                   # Schedule & calendar management
│   ├── archivist.py                 # File & data sovereignty
│   ├── cfo.py                       # Financial intelligence (Plaid, Empower, Rocket Money)
│   ├── cfo_dashboard.py             # Excel financial dashboards (openpyxl)
│   ├── device_agent.py              # IoT/LAN/smart home device management + automation
│   ├── doordash.py                  # Meal delivery coordination
│   ├── gmail_agent.py               # Email & inbox monitoring
│   ├── web_architect.py             # Website security & n8n deployment
│   └── website_manager.py           # Per-site build/deploy pipelines
├── core/                            # System infrastructure
│   ├── guardian.py                   # Central coordinator (GuardianOne class)
│   ├── base_agent.py                # Agent contract (BaseAgent ABC)
│   ├── ai_engine.py                 # LLM reasoning layer (Ollama primary, Anthropic fallback)
│   ├── cfo_router.py                # Natural-language CFO command router (keyword/regex, no LLM)
│   ├── mediator.py                  # Cross-agent conflict resolution
│   ├── scheduler.py                 # Agent scheduling (interval-based)
│   ├── sandbox.py                   # Deployment testing
│   ├── evaluator.py                 # Performance metrics
│   ├── audit.py                     # Immutable audit logging (append-only, severity-tagged)
│   ├── security.py                  # Access control & authentication
│   ├── security_remediation.py      # Domain-level threat tracking & verification
│   └── config.py                    # Configuration management (load_config, AgentConfig)
├── integrations/                    # External service connectors
│   ├── notion_sync.py               # Write-only Notion workspace sync
│   ├── notion_website_sync.py       # Per-site Notion dashboards
│   ├── notion_remediation_sync.py   # Security remediation → Notion tracker
│   ├── n8n_sync.py                  # n8n workflow automation
│   ├── financial_sync.py            # Plaid/Empower/Rocket Money sync
│   ├── plaid_connect.py             # Plaid Link bank account connection
│   ├── calendar_sync.py             # Google Calendar sync
│   ├── gmail_sync.py                # Gmail API
│   ├── doordash_sync.py             # DoorDash API
│   ├── ollama_sync.py               # Ollama model management (pull, delete, benchmark)
│   ├── ring_monitor.py              # Ring doorbell/camera monitoring
│   └── privacy_tools.py             # VPN/privacy services
├── homelink/                        # H.O.M.E. L.I.N.K. smart home service layer
│   ├── gateway.py                   # API gateway (rate limit, TLS, circuit breaker)
│   ├── vault.py                     # Encrypted credential storage (AES-256-GCM)
│   ├── registry.py                  # Integration catalog with threat models
│   ├── monitor.py                   # System health monitoring
│   ├── devices.py                   # IoT device inventory & room model
│   ├── drivers.py                   # Device protocol drivers (Kasa, Hue, Govee, RTSP)
│   ├── automations.py               # Schedule-driven automation engine (wake/sleep/leave/arrive)
│   ├── email_commands.py            # Email-based device control
│   └── lan_security.py              # LAN/VLAN security enforcement
├── templates/                       # Agent creation templates
│   └── agent_template.py            # Boilerplate for new agents
├── web/                             # Web-based dev panel
│   └── app.py                       # Flask dev panel (--devpanel, port 5100)
└── utils/                           # Shared utilities
    ├── encryption.py                # File-level encryption (Fernet/PBKDF2)
    └── notifications.py             # Multi-channel alerts (Console, Email, SMS, iMessage, Push)

config/
├── guardian_config.yaml             # Agent & system configuration
data/
├── cfo_ledger.json                  # Financial ledger (accounts, transactions, bills)
docs/
├── GUARDIAN_ONE_SYSTEM_PROMPT.md    # AI system prompt reference
├── deliverables/                    # Business deliverables (SHM Converge, business model, GTM)
└── security/                        # Security & privacy policies
scripts/
├── guardian_daemon.ps1              # Windows daemon script
└── inspect_mcp.sh                   # MCP server inspection helper
tests/                               # ~8600 lines of pytest tests (25+ test files)
```

### Root-Level Files

| File | Purpose |
|------|---------|
| `guardian_launcher.py` | Alternative launcher with guided setup |
| `guardian_learning.py` | Learning/training system (~45K lines) |
| `guardian_system.py` | System-level orchestration scripts |
| `guardian_agent_setup.py` | Agent setup & initialization |
| `guardian_skills.json` | Skill definitions for agents |
| `guardian_errors.json` | Error catalog |
| `ROADMAP_LIVE.md` | 10-step production roadmap |
| `BRIEF.md` / `EXECUTIVE_BRIEF.md` | Project briefings |

## MCP Server

Guardian One exposes an MCP server (`mcp_server.py`) for integration with Claude and other MCP clients:

```bash
python mcp_server.py                    # stdio transport (default)
python mcp_server.py --transport sse    # SSE transport on port 8080
npx @modelcontextprotocol/inspector python mcp_server.py  # Inspect tools
```

**Exposed MCP tools:** `system_status`, `list_agents`, `run_agent`, `daily_summary`,
`audit_log`, `pending_reviews`, `security_audit`, `vault_health`, `gateway_status`

## AI Engine

The AI Engine (`core/ai_engine.py`) provides a unified reasoning interface:
- **Primary:** Ollama (local, sovereign) — `ollama_model: llama3`
- **Fallback:** Anthropic Claude API (cloud)
- Per-agent conversation memory, automatic failover
- Configurable in `guardian_config.yaml` under `ai_engine:`

## Smart Home (H.O.M.E. L.I.N.K.)

Full IoT device management via `DeviceAgent` + `homelink/` modules:

**Managed ecosystems:**
- TP-Link Kasa/Tapo (smart plugs) — local LAN API via `python-kasa`
- Philips Hue (smart lights) — Zigbee via Hue Bridge local API
- Govee (smart lights) — LAN UDP API
- Ryse SmartShade (smart blinds) — BLE/WiFi
- Security cameras — RTSP/ONVIP local streams
- Smart TV — LAN API
- Vehicle — OBD-II readonly
- Flipper Zero — USB serial, sub-GHz/NFC/IR/BLE security tool

**Automations:** Wake, sleep, leave, arrive routines driven by Chronos schedule events.

## Managed Websites

Two active web properties managed via `WebsiteManager` + `WebArchitect`:

| Domain | Type | Status | Purpose |
|--------|------|--------|---------|
| **drjeremytabernero.org** | Professional | Down (needs redeployment) | Personal/professional site, CV, publications |
| **jtmdai.com** | Business | Live | JTMD AI — AI solutions, services, case studies |

## Notifications

Multi-channel notification system (`utils/notifications.py`):
- **Channels:** Console, Email (Gmail SMTP), SMS (Twilio), iMessage (macOS), Push (webhook)
- **Features:** Quiet hours (10 PM–7 AM), rate limiting (3 per 2 hours), daily digest
- **AlertRouter:** Auto-generates notifications from CFO events (bills, budgets, suspicious txns)

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest/transit
2. **Write-only Notion** — Push operational data only, never read for decisions
3. **Content gate** — PHI/PII patterns blocked before any external sync
4. **Audit everything** — Immutable log of all agent actions
5. **On-demand credentials** — Tokens loaded from Vault per-request, never cached
6. **Agent isolation** — Each agent has defined `allowed_resources`
7. **Local-first IoT** — All smart home devices prefer local API over cloud
8. **Sovereign AI** — Ollama (local LLM) is primary; cloud is fallback only

## Security Architecture

- **Vault**: AES-256-GCM encrypted credential storage with per-credential scoping
- **Gateway**: TLS enforcement, rate limiting, circuit breakers for all external calls
- **Registry**: Every integration has a threat model (top 5 risks) and rollback procedure
- **Content Classification**: Regex-based PHI/PII scanner blocks sensitive data from sync
- **Audit Log**: Append-only, severity-tagged, immutable records
- **Security Remediation**: Domain-level threat tracking (email, Cloudflare, HTTP headers, infrastructure)
- **Connector Security**: MCP/Claude connector attack surface policy (required/evaluate/dangerous/disconnect)
- **LAN Security**: VLAN isolation for IoT, unknown device alerts, firmware monitoring

## Configuration

Primary config: `config/guardian_config.yaml`
Environment: `.env` (NOTION_TOKEN, API keys, GUARDIAN_MASTER_PASSPHRASE, etc.)

**Key env vars:** `NOTION_TOKEN`, `NOTION_ROOT_PAGE_ID`, `PLAID_CLIENT_ID`, `PLAID_SECRET`,
`GMAIL_APP_PASSWORD`, `ANTHROPIC_API_KEY`, `NOTIFY_PHONE`, `TWILIO_*`

## Dependencies

**Core:** `pyyaml`, `cryptography`, `python-dotenv`, `schedule`, `rich`
**Financial:** `openpyxl` (Excel dashboards)
**Web:** `flask` (dev panel)
**AI:** `ollama`, `anthropic`, `httpx`
**MCP:** `mcp` (Model Context Protocol server)
**IoT:** `python-kasa`, `phue`
**Dev:** `pytest`, `pytest-asyncio`

## Running Tests

```bash
pytest tests/ -v                            # All tests (~8600 lines across 25+ files)
pytest tests/test_website_manager.py        # Website manager tests
pytest tests/test_homelink.py               # H.O.M.E. L.I.N.K. tests
pytest tests/test_devices.py                # IoT device tests
pytest tests/test_ai_engine.py              # AI engine tests
pytest tests/test_cfo_router.py             # CFO conversational router
pytest tests/test_financial_sync.py         # Financial sync tests
pytest tests/test_calendar_sync.py          # Calendar sync tests (largest test file)
pytest tests/test_notifications.py          # Notification system tests
pytest tests/test_security_remediation.py   # Security remediation tests
pytest tests/test_ollama_sync.py            # Ollama integration tests
```

Tests use fake providers (no real API calls). Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`.

## Common CLI Commands

```bash
# Core operations
python main.py                              # Run all agents once and print daily summary
python main.py --schedule                   # Start interactive scheduler
python main.py --summary                    # Print daily summary only
python main.py --agent NAME                 # Run a single agent by name

# Financial (CFO)
python main.py --cfo                        # Interactive CFO assistant (conversational REPL)
python main.py --dashboard                  # Generate CFO Excel dashboard
python main.py --dashboard-password PASS    # Password-protected Excel dashboard
python main.py --validate                   # CFO validation report (detailed)
python main.py --sync                       # Continuous financial sync loop (5min intervals)
python main.py --sync-once                  # Single sync cycle
python main.py --connect                    # Connect bank accounts via Plaid
python main.py --cfo-clean                  # Clean ledger (strip sandbox data, zero-balance dupes)
python main.py --cfo-clean-dry              # Preview cleanup without changes
python main.py --csv PATH                   # Parse Rocket Money CSV
python main.py --xlsx PATH                  # Import Rocket Money XLSX

# Calendar & Email
python main.py --calendar                   # Today's schedule
python main.py --calendar-week              # This week's schedule
python main.py --calendar-sync              # Sync Google Calendar + push bills
python main.py --calendar-auth              # Google Calendar OAuth flow
python main.py --gmail                      # Gmail inbox + Rocket Money CSV check

# Notifications
python main.py --notify                     # Run daily review and send notifications
python main.py --notify-test                # Test notification delivery

# Websites
python main.py --websites                   # Show all site status
python main.py --website-build DOMAIN       # Build a site (or 'all')
python main.py --website-deploy DOMAIN      # Deploy a site (or 'all')
python main.py --website-sync               # Push website dashboards to Notion
python main.py --notion-sync                # Full Notion workspace sync
python main.py --notion-preview             # Preview Notion pages (no API needed)

# Smart Home (H.O.M.E. L.I.N.K.)
python main.py --homelink                   # H.O.M.E. L.I.N.K. service status
python main.py --devices                    # Full IoT device dashboard
python main.py --device-audit               # Device security audit
python main.py --rooms                      # Room layout with devices
python main.py --scene movie                # Activate a scene (movie, work, away, goodnight)
python main.py --home-event wake            # Fire event (wake, sleep, leave, arrive, sunrise, sunset)
python main.py --flipper                    # Flipper Zero device profiles

# Security
python main.py --brief                      # H.O.M.E. L.I.N.K. weekly security brief
python main.py --security-review            # Security remediation review (all domains)
python main.py --security-review DOMAIN     # Security review for one domain
python main.py --security-sync              # Push remediation status to Notion
python main.py --connector-audit            # Audit Claude connector/MCP attack surface
python main.py --sandbox                    # Deploy agents in sandbox + start eval loop

# AI Engine
python main.py --ollama                     # Ollama status + models
python main.py --ollama-benchmark [MODEL]   # Benchmark an Ollama model
python main.py --ollama-pull MODEL          # Pull a model from Ollama registry
python main.py --ollama-delete MODEL        # Delete a local model

# Dev Panel
python main.py --devpanel                   # Launch web-based dev panel (Flask, port 5100)
python main.py --devpanel-port PORT         # Custom port
```

## Development Notes

- Python 3.10+ (3.11+ recommended), no Docker yet (on roadmap)
- All agents extend `BaseAgent` (core/base_agent.py) with `initialize`/`run`/`report`
- Tests use fake providers (no real API calls)
- Config loaded via `load_config()` from `core/config.py`
- `AgentConfig` dataclass holds per-agent settings (enabled, schedule, allowed_resources, custom)
- Multi-device: This CLAUDE.md carries full context across machines via git
- `pyproject.toml` defines the package with `guardian` console script entry point
- Async I/O used in some integrations; pytest uses `asyncio_mode = "auto"`

## Adding a New Agent

1. Create `guardian_one/agents/your_agent.py` extending `BaseAgent`
2. Implement `initialize()`, `run()`, and `report()` methods
3. Add config section in `config/guardian_config.yaml` under `agents:`
4. Register in `_build_agents()` in `main.py` and `mcp_server.py`
5. Add tests in `tests/test_your_agent.py`
6. See `guardian_one/templates/agent_template.py` for boilerplate

## Cross-Device Setup

Clone on any machine and Claude Code will understand the project:
```bash
git clone <repo-url> ~/JT
cd ~/JT
# Claude Code reads this CLAUDE.md automatically
```

Both machines (current + ROG X 64GB) share context through this repo.
Always pull latest before starting work on a new device.
