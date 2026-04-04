# CLAUDE.md

## What This Is

Guardian One is a **multi-agent AI orchestration platform** for personal life management,
built for Jeremy Paulo Salvino Tabernero. It coordinates autonomous agents that handle
finance, scheduling, email, meals, websites, IoT/smart-home devices, and data sovereignty
— all with encryption, audit trails, and zero data exploitation.

## Owner

Jeremy Paulo Salvino Tabernero
Timezone: America/Chicago

## Architecture

```
main.py                             # CLI entry point (35+ commands)
mcp_server.py                       # MCP server (stdio/SSE) — exposes Guardian tools to Claude
guardian_one/
├── agents/                         # Subordinate agents
│   ├── chronos.py                  # Schedule & calendar management
│   ├── archivist.py                # File & data sovereignty
│   ├── cfo.py                      # Financial intelligence (Plaid, Empower, Rocket Money)
│   ├── cfo_dashboard.py            # Excel financial dashboards (openpyxl)
│   ├── doordash.py                 # Meal delivery coordination
│   ├── gmail_agent.py              # Email & inbox monitoring
│   ├── device_agent.py             # IoT/smart-home device management
│   ├── web_architect.py            # Website security & n8n deployment
│   └── website_manager.py          # Per-site build/deploy pipelines
├── core/                           # System infrastructure
│   ├── guardian.py                  # Central coordinator (registers agents, runs orchestration)
│   ├── base_agent.py               # Agent contract (BaseAgent ABC: initialize/run/report)
│   ├── ai_engine.py                # Sovereign AI reasoning (Ollama primary, Claude fallback)
│   ├── cfo_router.py               # Natural-language CFO query routing
│   ├── mediator.py                 # Cross-agent conflict resolution
│   ├── scheduler.py                # Agent scheduling (interval-based)
│   ├── sandbox.py                  # Deployment testing
│   ├── evaluator.py                # Performance metrics
│   ├── audit.py                    # Immutable audit logging (severity-tagged)
│   ├── security.py                 # Access control & encryption
│   ├── security_remediation.py     # Security task tracking & verification
│   └── config.py                   # Configuration management (load_config / AgentConfig)
├── integrations/                   # External service connectors
│   ├── notion_sync.py              # Write-only Notion workspace sync
│   ├── notion_website_sync.py      # Per-site Notion dashboards
│   ├── notion_remediation_sync.py  # Security remediation → Notion
│   ├── n8n_sync.py                 # n8n workflow automation
│   ├── financial_sync.py           # Plaid/Empower/Rocket Money
│   ├── calendar_sync.py            # Google Calendar
│   ├── gmail_sync.py               # Gmail API
│   ├── doordash_sync.py            # DoorDash API
│   ├── ollama_sync.py              # Ollama local LLM integration
│   ├── plaid_connect.py            # Plaid bank account linking
│   ├── ring_monitor.py             # Ring security camera monitoring
│   └── privacy_tools.py            # VPN/privacy services
├── homelink/                       # H.O.M.E. L.I.N.K. smart-home service layer
│   ├── gateway.py                  # API gateway (rate limit, TLS, circuit breaker)
│   ├── vault.py                    # Fernet/PBKDF2-encrypted credential storage
│   ├── registry.py                 # Integration catalog with threat models
│   ├── monitor.py                  # System health monitoring
│   ├── devices.py                  # IoT device inventory & lifecycle
│   ├── drivers.py                  # Device drivers (Kasa, Hue, Govee, Flipper)
│   ├── automations.py              # Scene engine & event triggers
│   ├── lan_security.py             # LAN/VLAN security auditing
│   └── email_commands.py           # Email-based device commands
├── web/                            # Web-based dev panel (Flask)
│   ├── app.py                      # Dev panel server (port 5100)
│   └── templates/
│       ├── panel.html              # Main dashboard template
│       └── homelink.html           # H.O.M.E. L.I.N.K. dashboard
├── templates/                      # Agent scaffolding
│   └── agent_template.py           # New agent boilerplate
└── utils/                          # Shared utilities
    ├── encryption.py               # Encryption helpers
    └── notifications.py            # Email/SMS/push notification dispatch
config/
├── guardian_config.yaml            # Agent & system configuration
├── .env.example                    # Environment variable template
scripts/
├── guardian_daemon.ps1             # Windows daemon scheduler (PowerShell)
├── inspect_mcp.sh                  # MCP inspector launch helper
data/
├── cfo_ledger.json                 # Financial ledger (daily net-worth snapshots)
logs/                               # Agent logs (gitignored except .gitkeep)
tests/                              # Test suite
docs/
└── deliverables/
    └── 03_GO_TO_MARKET.md          # Go-to-market strategy doc
```

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest and in transit
2. **Write-only Notion** — Push operational data only, never read for decisions
3. **Content gate** — PHI/PII patterns blocked before any external sync
4. **Audit everything** — Immutable log of all agent actions
5. **On-demand credentials** — Tokens loaded from the encrypted Vault on demand and not persisted in plaintext or stored long-term on agent objects
6. **Agent isolation** — Each agent has defined `allowed_resources`
7. **Local-first AI** — Ollama (local) is the primary AI provider; Claude API is the cloud fallback

## Agent System

All agents extend `BaseAgent` (`core/base_agent.py`) which defines three lifecycle methods:
- `initialize()` — Setup and resource loading
- `run()` — Main execution logic
- `report()` — Generate status report

Agents are registered with `GuardianOne` (the coordinator) via `register_agent()` in `main.py`.

### Registered Agents

| Agent | File | Purpose |
|-------|------|---------|
| Chronos | `agents/chronos.py` | Calendar, scheduling, routines |
| Archivist | `agents/archivist.py` | File management, data sovereignty, privacy |
| CFO | `agents/cfo.py` | Financial intelligence, net-worth tracking, bills |
| DoorDash | `agents/doordash.py` | Meal delivery coordination |
| Gmail | `agents/gmail_agent.py` | Inbox monitoring, Rocket Money CSV parsing |
| WebArchitect | `agents/web_architect.py` | Website security, n8n workflows, deployments |
| DeviceAgent | `agents/device_agent.py` | IoT/smart-home device management |

## AI Engine

The AI Engine (`core/ai_engine.py`) provides `ai.reason()` for LLM-powered reasoning:
- **Primary**: Ollama (local, `llama3`) — true data sovereignty
- **Fallback**: Anthropic Claude API — smarter but sends data externally
- Supports per-agent conversation memory
- Config in `guardian_config.yaml` under `ai_engine:`

## MCP Server

`mcp_server.py` exposes Guardian One capabilities via the Model Context Protocol:
```bash
python mcp_server.py                    # stdio transport (default)
python mcp_server.py --transport sse    # SSE transport on port 8080
npx @modelcontextprotocol/inspector python mcp_server.py  # Inspect tools
```

## H.O.M.E. L.I.N.K. (Smart Home)

Full IoT management layer in `guardian_one/homelink/`:
- **Devices**: Inventory, health monitoring, firmware tracking
- **Drivers**: TP-Link Kasa, Philips Hue, Govee, Flipper Zero (all local-first)
- **Automations**: Scenes (movie, work, away, goodnight) and events (wake, sleep, sunrise, sunset)
- **LAN Security**: VLAN enforcement, unknown device alerting, telemetry blocking
- **Email Commands**: Remote device control via email

## Managed Websites

Two active web properties managed via `WebsiteManager` + `WebArchitect`:

| Domain | Type | Status | Purpose |
|--------|------|--------|---------|
| **drjeremytabernero.org** | Professional | Down (needs redeployment) | Personal/professional site, CV, publications |
| **jtmdai.com** | Business | Live | JTMD AI — AI solutions, services, case studies |

## Agent Pattern

- **Vault**: AES-256-GCM encrypted credential storage with per-credential scoping
- **Gateway**: TLS enforcement, rate limiting, circuit breakers for all external calls
- **Registry**: Every integration has a threat model (top 5 risks) and rollback procedure
- **Content Classification**: Regex-based PHI/PII scanner blocks sensitive data from sync
- **Audit Log**: Append-only, severity-tagged, immutable records
- **Connector Audit**: Attack surface review for all Claude/MCP connectors
- **Security Remediation**: Tracked per-domain with Notion sync and automated verification

## Configuration

- **Primary config**: `config/guardian_config.yaml`
- **Environment**: `.env` (NOTION_TOKEN, API keys, etc.) — see `config/.env.example`
- **Config loading**: `load_config()` from `core/config.py` returns typed config object

## Flask Integration

```bash
pytest tests/ -v                          # All tests (721 test functions across 26 files)
pytest tests/test_agents.py               # All agent tests
pytest tests/test_guardian.py             # Core guardian tests
pytest tests/test_homelink.py             # H.O.M.E. L.I.N.K. tests
pytest tests/test_devices.py              # Device management tests
pytest tests/test_ai_engine.py            # AI engine tests
pytest tests/test_cfo_router.py           # CFO router tests
pytest tests/test_security_remediation.py # Security remediation tests
```

Tests use fake providers (no real API calls). Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`.

## Common CLI Commands

```bash
# Core operations
python main.py                         # Run all agents once
python main.py --schedule              # Start agent scheduler
python main.py --agent NAME            # Run a single agent
python main.py --summary               # Print daily summary

# Financial
python main.py --dashboard             # Generate CFO Excel dashboard
python main.py --validate              # CFO validation report (detailed)
python main.py --sync                  # Continuous financial sync
python main.py --connect               # Connect bank accounts via Plaid
python main.py --cfo                   # Interactive CFO assistant (conversational)
python main.py --csv PATH              # Parse Rocket Money CSV

# Calendar & Email
python main.py --calendar              # Today's schedule
python main.py --calendar-week         # This week's schedule
python main.py --calendar-sync         # Sync Google Calendar
python main.py --calendar-auth         # Authorize Google Calendar (OAuth)
python main.py --gmail                 # Gmail inbox status

# Websites
python main.py --websites              # Show all site status
python main.py --website-build DOMAIN  # Build a site (or 'all')
python main.py --website-deploy DOMAIN # Deploy a site (or 'all')
python main.py --website-sync          # Push website dashboards to Notion
python main.py --notion-sync           # Full Notion workspace sync

# Smart Home (H.O.M.E. L.I.N.K.)
python main.py --devices               # Full device dashboard
python main.py --device-audit          # Device security audit
python main.py --rooms                 # Room layout with devices
python main.py --scene movie           # Activate a scene (movie, work, away, goodnight)
python main.py --home-event wake       # Fire event (wake, sleep, leave, arrive, sunrise, sunset)
python main.py --flipper               # Flipper Zero device profiles
python main.py --homelink              # H.O.M.E. L.I.N.K. service status
python main.py --brief                 # Weekly security brief

# Security
python main.py --security-review       # Security remediation review (all domains)
python main.py --security-review DOMAIN # Review a single domain
python main.py --security-sync         # Push remediation status to Notion
python main.py --connector-audit       # Audit Claude connector attack surface

# Notifications
python main.py --notify                # Daily review + notifications (email/SMS)
python main.py --notify-test           # Test notification delivery

# Dev Panel
python main.py --devpanel              # Start web dev panel (port 5100)
python main.py --sandbox               # Deploy in sandbox for testing
```

## Dependencies

Core (`pyproject.toml`):
- `pyyaml`, `cryptography`, `python-dotenv`, `schedule`, `rich`

Full (`requirements.txt` adds):
- `openpyxl` (Excel dashboards), `flask` (dev panel)
- `ollama`, `anthropic`, `httpx` (AI engine)
- `mcp` (MCP server)
- `python-kasa`, `phue` (smart home drivers)
- `pytest`, `pytest-asyncio` (dev)

Requires **Python 3.10+** (3.11+ recommended).

## CI/CD

- **GitHub Actions**: `.github/workflows/compose-health-check.yml` — runs on push/PR to `main` when `docker-compose.yml` changes; validates n8n + Postgres health via docker compose.

## Development Notes

- All agents extend `BaseAgent` with `initialize`/`run`/`report`
- Tests use fake providers — no real API calls in test suite
- Config loaded via `load_config()` from `core/config.py`
- New agents can be scaffolded from `guardian_one/templates/agent_template.py`
- Multi-device: This CLAUDE.md carries full context across machines via git
- Financial ledger snapshots stored in `data/cfo_ledger.json` (daily net-worth tracking)
- Log backups: `guardian_one_log_backup_*.json` files in project root

| Domain | Purpose |
|--------|---------|
| drjeremytabernero.org | Professional site, CV, publications |
| jtmdai.com | JTMD AI — AI solutions, services |

## Cross-Device

This CLAUDE.md carries full context across machines via git. Always pull latest before starting work on a new device. Both machines (current + ROG X 64GB) share context through this repo.
