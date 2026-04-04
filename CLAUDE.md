# Guardian One — Claude Code Project Context

## What This Is

Guardian One is a **multi-agent AI orchestration platform** for personal life management,
built for Jeremy Paulo Salvino Tabernero. It coordinates autonomous agents that handle
finance, scheduling, email, meals, websites, smart home devices, and data sovereignty —
all with encryption, audit trails, and zero data exploitation.

## Owner

Jeremy Paulo Salvino Tabernero
Timezone: America/Chicago

## CLAUDE.md Maintenance

This file is maintained by the **Archivist** agent (`guardian_one/agents/archivist.py`).
The Archivist is responsible for keeping this document in sync with the current state of
the codebase whenever structural changes occur (new agents, modules, integrations, etc.).

## Architecture

```
main.py                              # CLI entry point (25+ commands)
mcp_server.py                       # Model Context Protocol server (Inspector support)
guardian_one/
├── agents/                          # Subordinate agents
│   ├── chronos.py                   # Schedule & calendar management
│   ├── archivist.py                 # File & data sovereignty
│   ├── cfo.py                       # Financial intelligence (Plaid, Empower, Rocket Money)
│   ├── cfo_dashboard.py             # Excel financial dashboards
│   ├── device_agent.py              # Smart home device management
│   ├── doordash.py                  # Meal delivery coordination
│   ├── gmail_agent.py               # Email & inbox monitoring
│   ├── web_architect.py             # Website security & n8n deployment
│   └── website_manager.py           # Per-site build/deploy pipelines
├── core/                            # System infrastructure
│   ├── guardian.py                   # Central coordinator/orchestrator
│   ├── base_agent.py                # Agent contract (BaseAgent ABC)
│   ├── ai_engine.py                 # AI reasoning (Ollama primary + Anthropic fallback)
│   ├── mediator.py                  # Cross-agent conflict resolution
│   ├── scheduler.py                 # Agent scheduling & intervals
│   ├── sandbox.py                   # Deployment testing & validation
│   ├── evaluator.py                 # Performance metrics (5-point scale)
│   ├── audit.py                     # Immutable audit logging with severity tags
│   ├── security.py                  # Access control & authentication
│   ├── security_remediation.py      # Security issue tracking & remediation
│   ├── cfo_router.py                # Financial data routing
│   └── config.py                    # Configuration management
├── integrations/                    # External service connectors
│   ├── notion_sync.py               # Write-only Notion workspace sync
│   ├── notion_website_sync.py       # Per-site Notion dashboards
│   ├── notion_remediation_sync.py   # Security remediation Notion sync
│   ├── n8n_sync.py                  # n8n workflow automation
│   ├── financial_sync.py            # Plaid/Empower/Rocket Money
│   ├── calendar_sync.py             # Google Calendar
│   ├── gmail_sync.py                # Gmail API
│   ├── doordash_sync.py             # DoorDash API
│   ├── ollama_sync.py               # Local Ollama model sync
│   ├── plaid_connect.py             # Plaid bank account connection
│   ├── privacy_tools.py             # VPN/privacy services
│   └── ring_monitor.py              # Ring doorbell monitoring
├── homelink/                        # H.O.M.E. L.I.N.K. service layer
│   ├── gateway.py                   # API gateway (rate limit, TLS, circuit breaker)
│   ├── vault.py                     # AES-256-GCM encrypted credential storage
│   ├── registry.py                  # Integration catalog with threat models
│   ├── monitor.py                   # System health monitoring
│   ├── devices.py                   # Smart device management
│   ├── drivers.py                   # Device driver interface
│   ├── automations.py               # Automation rules engine
│   ├── email_commands.py            # Email-based command interface
│   └── lan_security.py              # LAN security & network isolation
├── templates/                       # Agent scaffolding
│   └── agent_template.py            # Template for creating new agents
├── utils/                           # Shared utilities
│   ├── encryption.py                # Encryption utilities
│   └── notifications.py             # Notification channels (Email, SMS, iMessage, Push)
└── web/                             # Web interface
    ├── app.py                       # Flask web application
    └── templates/
        ├── panel.html               # Device control panel
        └── homelink.html            # H.O.M.E. L.I.N.K. dashboard
config/
├── guardian_config.yaml             # Agent & system configuration
├── .env.example                     # Environment variables template
data/                                # Runtime data (cfo_ledger.json, etc.)
logs/                                # Application logs
scripts/
├── inspect_mcp.sh                   # MCP server inspection
└── guardian_daemon.ps1              # Windows PowerShell daemon
docs/
├── GUARDIAN_ONE_SYSTEM_PROMPT.md    # AI system prompt documentation
├── deliverables/                    # Business planning documents
│   ├── 01_SHM_CONVERGE_2026.md
│   ├── 02_BUSINESS_MODEL.md
│   └── 03_GO_TO_MARKET.md
└── security/                        # Security & privacy policies
    ├── INFORMATION_SECURITY_POLICY.md
    └── PRIVACY_POLICY.md
tests/                               # 203 pytest test cases (25 test files)
```

## Agent Contract

All agents extend `BaseAgent` (core/base_agent.py) which defines:

**Required lifecycle methods:**
1. `initialize()` — One-time setup (connect APIs, load state)
2. `run()` — Periodic execution cycle, returns `AgentReport`
3. `report()` — Structured report without side effects
4. `shutdown()` — Clean up resources

**Built-in AI reasoning:**
- `think(prompt, context, temperature, max_tokens)` — Get AI reasoning
- `think_quick(prompt, context)` — Quick one-shot reasoning (text only)
- Falls back gracefully if no AI engine available

**Agent system prompts** are defined per-agent in `AGENT_SYSTEM_PROMPTS` dict within base_agent.py.

**Status tracking** via `AgentStatus` enum: IDLE, RUNNING, ERROR, DISABLED

## AI Engine

Configured in `guardian_config.yaml`:
- **Primary**: Ollama (local data sovereignty, model: llama3)
- **Fallback**: Anthropic (claude-sonnet-4-20250514)
- Temperature: 0.3 (deterministic), max tokens: 2048
- Memory: enabled, max 50 messages per agent

## Managed Websites

Two web properties managed via `WebsiteManager` + `WebArchitect`:

| Domain | Type | Purpose |
|--------|------|---------|
| **drjeremytabernero.org** | Professional | Personal/professional site, CV, publications |
| **jtmdai.com** | Business | JTMD AI — AI solutions, services, case studies |

### Website CLI Commands
```bash
python main.py --websites              # Show all site status
python main.py --website-build all     # Build all sites
python main.py --website-build drjeremytabernero.org  # Build one site
python main.py --website-deploy all    # Deploy all sites
python main.py --website-sync          # Push dashboards to Notion
```

### Website Notion Integration
Each site gets its own Notion dashboard page under a "Website Management" parent,
showing build status, page inventory, security posture, and deploy history.
All data passes through the content classification gate (no PHI/PII ever leaves).

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest/transit
2. **Write-only Notion** — Push operational data only, never read for decisions
3. **Content gate** — PHI/PII patterns blocked before any external sync
4. **Audit everything** — Immutable log of all agent actions
5. **On-demand credentials** — Tokens loaded from Vault per-request, never cached
6. **Agent isolation** — Each agent has defined allowed_resources
7. **Local-first AI** — Ollama preferred over cloud APIs for data sovereignty

## Security Architecture

- **Vault**: AES-256-GCM encrypted credential storage with per-credential scoping
- **Gateway**: TLS enforcement, rate limiting, circuit breakers for all external calls
- **Registry**: Every integration has a threat model (top 5 risks) and rollback procedure
- **Content Classification**: Regex-based PHI/PII scanner blocks sensitive data from sync
- **Audit Log**: Append-only, severity-tagged, immutable records
- **LAN Security**: Network isolation and monitoring for smart home devices
- **Security Remediation**: Tracked per-domain with Notion sync and auto-verify

## Configuration

Primary config: `config/guardian_config.yaml`
Environment template: `config/.env.example`
Runtime env: `.env` (NOTION_TOKEN, API keys, Plaid, Twilio, etc.)

### Notification System
- Channels: Email, SMS (Twilio), iMessage (macOS), Push
- Quiet hours: 22:00–07:00 (CRITICAL bypasses)
- Rate limit: 3 per 2-hour window

## Running Tests

```bash
pytest tests/ -v                              # All tests (203 passing)
pytest tests/test_website_manager.py          # Website manager
pytest tests/test_notion_website_sync.py      # Notion website sync
pytest tests/test_web_architect.py            # WebArchitect
pytest tests/test_homelink.py                 # H.O.M.E. L.I.N.K.
pytest tests/test_devices.py                  # Device management
pytest tests/test_security_remediation.py     # Security remediation
pytest tests/test_ai_engine.py                # AI engine
pytest tests/test_encryption.py               # Encryption utilities
pytest tests/test_notifications.py            # Notification channels
```

Tests use fake providers — no real API calls. Async tests via pytest-asyncio (mode: auto).

## Common CLI Commands

```bash
python main.py                         # Run all agents once
python main.py --schedule              # Start interactive agent scheduler
python main.py --dashboard             # Generate CFO Excel dashboard
python main.py --sync                  # Continuous financial sync
python main.py --calendar-sync         # Sync Google Calendar
python main.py --gmail                 # Gmail inbox status
python main.py --cfo                   # Interactive financial assistant
python main.py --websites              # Website management
python main.py --homelink              # H.O.M.E. L.I.N.K. status
python main.py --brief                 # Weekly security brief
python main.py --sandbox               # Sandbox deployment
python main.py --notify                # Daily notifications
```

## Dependencies

Key packages (see `requirements.txt` and `pyproject.toml`):
- **Core**: pyyaml, cryptography, python-dotenv, schedule, rich
- **AI**: ollama, anthropic, httpx
- **Web**: flask, mcp
- **Smart home**: python-kasa, phue
- **Dashboards**: openpyxl
- **Testing**: pytest, pytest-asyncio

## Development Notes

- Python >=3.10, no Docker yet (on roadmap)
- All agents extend `BaseAgent` (core/base_agent.py) with initialize/run/report/shutdown
- Tests use fake providers (no real API calls)
- Config loaded via `load_config()` from core/config.py
- MCP server (`mcp_server.py`) exposes Guardian One tools for external AI integration
- CLI entry point also installable as `guardian` via pyproject.toml
- Multi-device: This CLAUDE.md carries full context across machines via git

## Cross-Device Setup

Clone on any machine and Claude Code will understand the project:
```bash
git clone <repo-url> ~/JT
cd ~/JT
# Claude Code reads this CLAUDE.md automatically
```

Both machines (current + ROG X 64GB) share context through this repo.
Always pull latest before starting work on a new device.

### ASUS ROG X (64GB) — Archivist Duties

The Archivist agent secures, maintains, monitors, and guards the file system on the
ASUS ROG machine. Responsibilities include:
- **File system integrity** — Monitor for unauthorized changes, corruption, or drift
- **Data sovereignty enforcement** — Ensure sensitive files remain encrypted at rest
- **Backup verification** — Validate that critical data and config are recoverable
- **CLAUDE.md stewardship** — Keep this file accurate as the codebase evolves
- **Audit trail** — Log all file system operations through the immutable audit log
