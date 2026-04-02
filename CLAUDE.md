# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Guardian One is a **multi-agent AI orchestration platform** for personal life management, built for Jeremy Paulo Salvino Tabernero (Timezone: America/Chicago). It coordinates autonomous agents handling finance, scheduling, email, meals, websites, smart home, and document search — with encryption, audit trails, and zero data exploitation.

The system also powers the **SMH JTMDAI clinical platform** — AI-assisted care transitions to reduce hospital readmissions, with a hospitalist-facing presentation for SHM Converge 2026.

## Build & Test Commands

```bash
# Run all agents once
python main.py

# Run tests (200+ in tests/, 3000+ in search/tests/)
python -m pytest tests/ -v
python -m pytest search/tests/ -v
python -m pytest tests/test_web_architect.py -v         # Single test file
python -m pytest tests/test_cfo_router.py::TestCFORouter::test_net_worth -v  # Single test

# Start services
python main.py --schedule              # Agent scheduler (interactive)
python main.py --devpanel              # Flask dev panel on port 5100
python main.py --devpanel --port 8080  # Custom port
python main.py --cfo                   # CFO conversational REPL
python main.py --sandbox               # Sandbox deploy + evaluator

# Document search PoC (no Docker required)
python search/server.py                # Whoosh-backed search on port 5200
python search/self_improve.py          # Run test-fix-retest pipeline

# Document search (production engines, requires Docker)
cd search/ && docker compose up -d     # Start Typesense + Meilisearch
pip install -r search/requirements.txt
python search/seed_documents.py --both # Seed both engines

# Website management
python main.py --websites              # Show site status
python main.py --website-build all     # Build all sites
python main.py --website-deploy all    # Deploy all sites
python main.py --website-sync          # Push dashboards to Notion
```

## Architecture

```
main.py                              # CLI entry point (25+ commands)
guardian_one/
├── agents/                          # Autonomous agents (all extend BaseAgent)
│   ├── chronos.py                   # Schedule & calendar
│   ├── archivist.py                 # File & data sovereignty
│   ├── cfo.py                       # Financial intelligence (Plaid, Empower)
│   ├── cfo_dashboard.py             # Excel financial dashboards
│   ├── device_agent.py              # Smart home device control
│   ├── doordash.py                  # Meal delivery
│   ├── gmail_agent.py               # Email monitoring
│   ├── web_architect.py             # Website security & n8n
│   └── website_manager.py           # Per-site build/deploy
├── core/                            # System infrastructure
│   ├── guardian.py                   # Central coordinator (registers all agents)
│   ├── base_agent.py                # Agent ABC: initialize() / run() / report()
│   ├── ai_engine.py                 # LLM layer: Ollama (primary) + Anthropic (fallback)
│   ├── cfo_router.py                # NL command routing (regex, no LLM needed)
│   ├── mediator.py                  # Cross-agent conflict resolution
│   ├── scheduler.py                 # Agent scheduling with pause/resume
│   ├── sandbox.py                   # Deployment testing
│   ├── evaluator.py                 # 5-point performance scoring
│   ├── audit.py                     # Immutable audit logging
│   ├── security.py                  # Access control
│   ├── security_remediation.py      # Auto-fix security findings
│   └── config.py                    # YAML config loader
├── integrations/                    # External service connectors
│   ├── ollama_sync.py               # Local LLM model management
│   ├── notion_sync.py               # Write-only Notion workspace sync
│   ├── notion_website_sync.py       # Per-site Notion dashboards
│   ├── notion_remediation_sync.py   # Security remediation sync
│   ├── financial_sync.py            # Plaid/Empower/Rocket Money
│   ├── plaid_connect.py             # Plaid Link integration
│   ├── calendar_sync.py             # Google Calendar
│   ├── gmail_sync.py                # Gmail API
│   ├── ring_monitor.py              # Ring security camera
│   └── n8n_sync.py                  # Workflow automation
├── homelink/                        # H.O.M.E. L.I.N.K. smart home layer
│   ├── gateway.py                   # API gateway (rate limit, TLS, circuit breaker)
│   ├── vault.py                     # AES-256-GCM encrypted credential storage
│   ├── registry.py                  # Integration catalog with threat models
│   ├── monitor.py                   # System health monitoring
│   ├── drivers.py                   # TP-Link Kasa, Philips Hue, Govee device drivers
│   ├── automations.py               # Schedule-driven room-based device control
│   ├── devices.py                   # Device registry and state
│   ├── lan_security.py              # Network security scanning
│   └── email_commands.py            # Email-triggered home commands
├── web/                             # Flask dev panel
│   ├── app.py                       # Web UI on port 5100
│   ├── search_routes.py             # Document search API blueprint
│   └── templates/                   # Jinja2 templates
└── utils/
    ├── encryption.py                # AES encryption helpers
    └── notifications.py             # Multi-channel alert system
search/                              # Document search subsystem
├── docker-compose.yml               # Typesense 27.1 + Meilisearch 1.12
├── server.py                        # Standalone Whoosh PoC server (port 5200)
├── seed_documents.py                # 10 sample clinical/compliance docs
├── self_improve.py                  # Test-fix-retest pipeline with logging
├── tests/test_search_comprehensive.py  # 3,099 parameterized tests
└── logs/                            # Pipeline improvement JSON + markdown logs
config/guardian_config.yaml          # Agent & system configuration
tests/                               # 200+ pytest cases (all use fake providers)
docs/
├── GUARDIAN_ONE_SYSTEM_PROMPT.md
├── deliverables/                    # SHM presentation, business model, GTM
├── security/                        # HIPAA, privacy policies
└── design/                          # Feature design specs
```

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest/transit
2. **Write-only Notion** — Push operational data only, never read for decisions
3. **Content gate** — PHI/PII regex scanner blocks sensitive data before any external sync
4. **Audit everything** — Immutable append-only log of all agent actions
5. **On-demand credentials** — Tokens loaded from Vault per-request, never cached
6. **Agent isolation** — Each agent has defined `allowed_resources` on its config
7. **Ollama-first AI** — Local LLM (sovereign), Anthropic as cloud fallback only

## Agent Pattern

All agents extend `BaseAgent` (core/base_agent.py) and implement:
- `initialize()` — setup, load config
- `run()` — main execution
- `report()` — return status dict

Agents are registered in `guardian.py` via `_build_agents()` and accessed through the central `GuardianOne` coordinator.

## Flask Integration

The web dev panel (`guardian_one/web/app.py`) runs on port 5100. To add new routes, register a blueprint:
```python
from guardian_one.web.search_routes import search_bp
app.register_blueprint(search_bp)
```

Search blueprint provides: `GET /search/typesense`, `GET /search/meilisearch`, `GET /search/ui/*`

## Configuration

- Primary config: `config/guardian_config.yaml`
- Environment: `.env` (NOTION_TOKEN, API keys — never commit)
- Config loaded via `load_config()` from `guardian_one/core/config.py`

## Managed Websites

| Domain | Purpose |
|--------|---------|
| drjeremytabernero.org | Professional site, CV, publications |
| jtmdai.com | JTMD AI — AI solutions, services |

## Cross-Device

This CLAUDE.md carries full context across machines via git. Always pull latest before starting work on a new device. Both machines (current + ROG X 64GB) share context through this repo.
