# Guardian One — Claude Code Project Context

## What This Is

Guardian One is a **multi-agent AI orchestration platform** for personal life management,
built for Jeremy Paulo Salvino Tabernero. It coordinates autonomous agents that handle
finance, scheduling, email, meals, websites, IoT/smart-home, and data sovereignty — all
with encryption, audit trails, and zero data exploitation.

## Owner

Jeremy Paulo Salvino Tabernero
Timezone: America/Chicago

## Architecture

```
main.py                              # CLI entry point (40+ commands)
guardian_one/
├── agents/                          # Subordinate agents
│   ├── chronos.py                   # Schedule & calendar management
│   ├── archivist.py                 # File & data sovereignty
│   ├── cfo.py                       # Financial intelligence (Plaid, Empower, Rocket Money)
│   ├── cfo_dashboard.py             # Excel financial dashboards (openpyxl)
│   ├── device_agent.py              # IoT/smart-home device control agent
│   ├── doordash.py                  # Meal delivery coordination
│   ├── gmail_agent.py               # Email & inbox monitoring
│   ├── web_architect.py             # Website security & n8n deployment
│   └── website_manager.py           # Per-site build/deploy pipelines
├── core/                            # System infrastructure
│   ├── guardian.py                   # Central coordinator
│   ├── base_agent.py                # Agent contract (BaseAgent ABC)
│   ├── ai_engine.py                 # Sovereign AI reasoning (Ollama primary, Anthropic fallback)
│   ├── cfo_router.py                # Natural-language CFO command router (regex, no LLM)
│   ├── mediator.py                  # Cross-agent conflict resolution
│   ├── scheduler.py                 # Agent scheduling (daemon mode support)
│   ├── sandbox.py                   # Deployment testing
│   ├── evaluator.py                 # Performance metrics
│   ├── audit.py                     # Immutable audit logging
│   ├── security.py                  # Access control
│   ├── security_remediation.py      # Security finding tracker with remediation workflows
│   └── config.py                    # Configuration management
├── integrations/                    # External service connectors
│   ├── notion_sync.py               # Write-only Notion workspace sync
│   ├── notion_website_sync.py       # Per-site Notion dashboards
│   ├── notion_remediation_sync.py   # Security remediation → Notion sync
│   ├── n8n_sync.py                  # n8n workflow automation
│   ├── financial_sync.py            # Plaid/Empower/Rocket Money
│   ├── plaid_connect.py             # Plaid Link bank connection flow
│   ├── calendar_sync.py             # Google Calendar
│   ├── gmail_sync.py                # Gmail API
│   ├── doordash_sync.py             # DoorDash API
│   ├── ollama_sync.py               # Ollama local LLM management
│   ├── ring_monitor.py              # Ring camera/doorbell integration
│   ├── privacy_tools.py             # VPN/privacy services
│   └── (future connectors)
├── homelink/                        # H.O.M.E. L.I.N.K. smart-home layer
│   ├── gateway.py                   # API gateway (rate limit, TLS, circuit breaker)
│   ├── vault.py                     # Encrypted credential storage (AES-256-GCM)
│   ├── registry.py                  # Integration catalog with threat models
│   ├── monitor.py                   # System health monitoring
│   ├── devices.py                   # IoT device inventory & room model
│   ├── drivers.py                   # Hardware drivers (Kasa, Hue, Ryse, Flipper Zero)
│   ├── automations.py               # Schedule-driven room-based device control
│   ├── lan_security.py              # LAN/network security auditing
│   └── email_commands.py            # Email-triggered device commands
├── templates/                       # Agent scaffolding
│   └── agent_template.py            # Template for creating new agents
├── utils/                           # Shared utilities
│   ├── encryption.py                # Encryption helpers
│   └── notifications.py             # Email/SMS notification delivery
├── web/                             # Web UI
│   └── app.py                       # Flask dev panel (port 5100)
config/
├── guardian_config.yaml             # Agent & system configuration
data/
├── cfo_ledger.json                  # Financial ledger (accounts, bills, transactions)
docs/
├── GUARDIAN_ONE_SYSTEM_PROMPT.md    # Master system prompt
├── deliverables/                    # Business docs (SHM Converge, business model, GTM)
└── security/                        # Security & privacy policies
scripts/
├── guardian_daemon.ps1              # Windows daemon launcher
logs/                                # Runtime log output
tests/                               # ~110+ pytest test cases (16 test files)
```

### Root-level scripts (learning/setup artifacts)

```
guardian_launcher.py                 # Alternative launcher / bootstrapper
guardian_learning.py                 # Learning/training scripts
guardian_lesson_2.py                 # Lesson modules (iterative builds)
guardian_lesson_3.py
guardian_one_lesson.py
guardian_system.py                   # System prompt / configuration scripts
guardian_agent_setup.py              # Agent provisioning scripts
guardian_test.py                     # Standalone test harness
guardian_skills.json                 # Skill/capability catalog (JSON)
guardian_errors.json                 # Error catalog
guardian_one_log.json                # Runtime log snapshots
```

## Managed Websites

Two active web properties managed via `WebsiteManager` + `WebArchitect`:

| Domain | Type | Purpose |
|--------|------|---------|
| **drjeremytabernero.org** | Professional | Personal/professional site, CV, publications |
| **jtmdai.com** | Business | JTMD AI — AI solutions, services, case studies |

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
7. **Sovereign AI first** — Local Ollama models preferred, cloud APIs as fallback only

## AI Engine

The AI Engine (`core/ai_engine.py`) provides a unified `reason()` interface for all agents:
- **Primary**: Ollama (local, self-hosted) — data never leaves the machine
- **Fallback**: Anthropic Claude API — used when Ollama is unavailable
- Handles provider selection, failover, and conversation memory
- Managed via `--ollama`, `--ollama-benchmark`, `--ollama-pull`, `--ollama-delete` CLI commands

## H.O.M.E. L.I.N.K. (Smart Home)

Full IoT/smart-home management subsystem:
- **Device inventory**: Cameras, smart plugs (Kasa), lights (Hue/Govee), blinds (Ryse), Flipper Zero, network gear
- **Room model**: Physical rooms → device groups with naming convention `{category}-{location}-{index}`
- **Automations**: Schedule-driven routines (wake, sleep, leave, arrive) via Chronos integration
- **Drivers**: TP-Link Kasa, Philips Hue, Ryse SmartShades, Flipper Zero profiles
- **LAN security**: Network audit, threat detection
- **Email commands**: Remote device control via email triggers

## Security Architecture

- **Vault**: AES-256-GCM encrypted credential storage with per-credential scoping
- **Gateway**: TLS enforcement, rate limiting, circuit breakers for all external calls
- **Registry**: Every integration has a threat model (top 5 risks) and rollback procedure
- **Content Classification**: Regex-based PHI/PII scanner blocks sensitive data from sync
- **Audit Log**: Append-only, severity-tagged, immutable records
- **Security Remediation**: Per-domain finding tracker with Notion sync (`--security-review`, `--security-sync`)
- **Connector Audit**: Attack surface analysis for all Claude/API integrations (`--connector-audit`)

## Configuration

Primary config: `config/guardian_config.yaml`
Environment: `.env` (NOTION_TOKEN, API keys, etc.)
Package metadata: `pyproject.toml` (Python >=3.10, setuptools build)

### Dependencies

Core: `pyyaml`, `cryptography`, `python-dotenv`, `schedule`, `rich`, `openpyxl`, `flask`
AI: `ollama`, `anthropic`, `httpx`
IoT: `python-kasa`, `phue`
Dev: `pytest`, `pytest-asyncio`

## Running Tests

```bash
pytest tests/ -v                             # All tests (~110+ collected)
pytest tests/test_cfo_router.py              # CFO conversational router
pytest tests/test_homelink.py                # H.O.M.E. L.I.N.K. devices/automations
pytest tests/test_ollama_sync.py             # Ollama integration
pytest tests/test_notion_remediation_sync.py # Security remediation sync
pytest tests/test_encryption.py              # Encryption utilities
pytest tests/test_devpanel.py                # Web dev panel
pytest tests/test_sandbox_eval.py            # Sandbox & evaluator
pytest tests/test_scheduler.py               # Agent scheduling
pytest tests/test_mediator.py                # Cross-agent mediation
pytest tests/test_doordash.py                # DoorDash agent
pytest tests/test_audit.py                   # Audit logging
pytest tests/test_notion_sync.py             # Notion sync
```

Tests use fake providers — no real API calls are made.

## CLI Commands — Full Reference

### Core
```bash
python main.py                         # Run all agents once and print daily summary
python main.py --schedule              # Start interactive agent scheduler
python main.py --summary               # Print daily summary only
python main.py --agent NAME            # Run a single agent by name
python main.py --config PATH           # Use a custom config YAML
```

### Financial (CFO)
```bash
python main.py --dashboard             # Generate CFO Excel dashboard
python main.py --dashboard-password PW # Password-protected Excel dashboard
python main.py --validate              # CFO validation report (detailed)
python main.py --cfo                   # Interactive CFO assistant (conversational REPL)
python main.py --cfo-clean             # Clean/deduplicate CFO ledger
python main.py --cfo-clean-dry         # Dry-run ledger cleanup
python main.py --cfo-connect           # Connect banks via Plaid Link
python main.py --sync                  # Continuous financial sync loop
python main.py --sync-once             # Single sync cycle then exit
python main.py --sync-interval N       # Sync interval in seconds (default: 300)
python main.py --connect               # Connect bank accounts via Plaid (read-only)
python main.py --csv PATH              # Parse local Rocket Money CSV
python main.py --xlsx PATH             # Import Rocket Money XLSX export
```

### Calendar & Email
```bash
python main.py --calendar              # Today's schedule + calendar status
python main.py --calendar-week         # This week's schedule
python main.py --calendar-sync         # Sync Google Calendar + push bills
python main.py --calendar-auth         # Authorize Google Calendar (OAuth)
python main.py --gmail                 # Gmail inbox status + Rocket Money CSV check
python main.py --notify                # Run daily review and send notifications
python main.py --notify-test           # Send test notification to verify setup
```

### Websites
```bash
python main.py --websites              # Show all site status
python main.py --website-build DOMAIN  # Build a site (or 'all')
python main.py --website-deploy DOMAIN # Deploy a site (or 'all')
python main.py --website-sync          # Push website dashboards to Notion
```

### H.O.M.E. L.I.N.K. (Smart Home)
```bash
python main.py --homelink              # H.O.M.E. L.I.N.K. service status
python main.py --devices               # Full device dashboard
python main.py --device-audit          # Run device security audit
python main.py --rooms                 # Show room layout with devices
python main.py --scene SCENE           # Activate scene (movie, work, away, goodnight)
python main.py --home-event EVENT      # Fire event (wake, sleep, leave, arrive, sunrise, sunset)
python main.py --flipper               # Flipper Zero device profiles
python main.py --brief                 # Weekly security brief
```

### Security
```bash
python main.py --security-review       # Security remediation review (all domains)
python main.py --security-review DOMAIN # Review a single domain
python main.py --security-sync         # Push remediation status to Notion
python main.py --connector-audit       # Audit Claude connector attack surface
```

### AI Engine (Ollama)
```bash
python main.py --ollama                # Ollama status + models
python main.py --ollama-benchmark      # Benchmark local models
python main.py --ollama-pull MODEL     # Pull model from Ollama registry
python main.py --ollama-delete MODEL   # Delete a local model
```

### Notion & Integrations
```bash
python main.py --notion-sync           # Full Notion workspace sync
python main.py --notion-preview        # Preview Notion pages (no API needed)
```

### Dev Tools
```bash
python main.py --devpanel              # Launch Flask web dev panel (port 5100)
python main.py --devpanel-port PORT    # Custom dev panel port
python main.py --sandbox               # Deploy agents in sandbox + start eval loop
```

## Development Notes

- Python 3.10+ (3.11+ recommended)
- All agents extend `BaseAgent` (core/base_agent.py) with `initialize()`, `run()`, `report()` methods
- New agents can be scaffolded from `templates/agent_template.py`
- Tests use fake providers (no real API calls)
- Config loaded via `load_config()` from `core/config.py`
- Web dev panel uses Flask on port 5100
- Multi-device: This CLAUDE.md carries full context across machines via git

## Cross-Device Setup

Clone on any machine and Claude Code will understand the project:
```bash
git clone <repo-url> ~/JT
cd ~/JT
pip install -r requirements.txt
# Claude Code reads this CLAUDE.md automatically
```

Both machines (current + ROG X 64GB) share context through this repo.
Always pull latest before starting work on a new device.
