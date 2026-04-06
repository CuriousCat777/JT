# CLAUDE.md

## What This Is

**Guardian One Operating System (GOOS) V1.0** — a multi-tenant AI operating system
that gives every user a personal AI command center. Built by Jeremy Paulo Salvino
Tabernero, GOOS coordinates autonomous agents across cloud and local machines.

Three pillars:
- **Guardian** — Central command AI (cloud). Coordinates all online agents.
- **Varys** — Local sentinel (always-on). Manages IoT, network security, physical world.
- **CFO** — Financial intelligence. Bank accounts, budgets, net-worth tracking.

Guardian is the brain online. Varys is the brain on your machines.

## Owner

Jeremy Paulo Salvino Tabernero
Timezone: America/Chicago

## Architecture

```
main.py                             # CLI entry point (35+ commands)
mcp_server.py                       # MCP server (stdio/SSE) — exposes Guardian tools to Claude
guardian_one/
├── goos/                       # GOOS platform layer (multi-tenant)
│   ├── client.py               # Client model, tiers, registry
│   ├── registration.py         # Account creation, verification, auth
│   ├── onboarding.py           # Guided onboarding (meet Guardian/CFO/Varys)
│   ├── sentinel.py             # Varys daemon/service manager
│   └── api.py                  # REST API for GOOS platform
├── agents/                     # Subordinate agents (cloud, managed by Guardian)
│   ├── chronos.py              # Schedule & calendar management
│   ├── archivist.py            # File & data sovereignty
│   ├── cfo.py                  # Financial intelligence (Plaid, Empower, Rocket Money)
│   ├── cfo_dashboard.py        # Excel financial dashboards
│   ├── doordash.py             # Meal delivery coordination
│   ├── gmail_agent.py          # Email & inbox monitoring
│   ├── dev_coach.py            # The Archivist — Developer Coach (Fireship-style)
│   ├── web_architect.py        # Website security & n8n deployment
│   └── website_manager.py      # Per-site build/deploy pipelines
├── core/                       # System infrastructure
│   ├── guardian.py              # Central coordinator (per-client in GOOS)
│   ├── base_agent.py           # Agent contract (BaseAgent ABC)
│   ├── ai_engine.py            # Ollama (local) + Claude (cloud) AI reasoning
│   ├── mediator.py             # Cross-agent conflict resolution
│   ├── scheduler.py            # Agent scheduling
│   ├── citadel.py              # SQLite backup/restore
│   ├── audit.py                # Immutable audit logging
│   ├── security.py             # Access control + encryption
│   ├── db_schema.py            # ACID SQL + Neo4j + Dgraph graph schemas
│   └── config.py               # Configuration management
├── varys/                      # Varys — local sentinel subsystems
│   ├── agent.py                # VarysAgent (BaseAgent) — security sentinel
│   ├── detection/              # Sigma rules, anomaly detection, risk scoring
│   ├── response/               # Automated containment + alerting
│   ├── brain/                  # LLM-powered triage
│   ├── ingestion/              # Auth log collection
│   └── api/                    # Flask security dashboard + chat UI
├── homelink/                   # H.O.M.E. L.I.N.K. — Varys's IoT interface
│   ├── gateway.py              # API gateway (rate limit, TLS, circuit breaker)
│   ├── vault.py                # Encrypted credential storage
│   ├── registry.py             # Integration catalog with threat models
│   ├── monitor.py              # System health monitoring
│   ├── devices.py              # IoT device inventory
│   ├── iot_controller.py       # Docker Compose IoT orchestration
│   ├── automations.py          # Scenes and automations
│   ├── drivers.py              # Device-specific drivers (Hue, WebOS, etc.)
│   ├── network_monitor.py      # Network traffic monitoring
│   └── network_scanner.py      # LAN scanning
├── integrations/               # External service connectors
│   ├── notion_sync.py          # Write-only Notion workspace sync
│   ├── financial_sync.py       # Plaid/Empower/Rocket Money
│   ├── calendar_sync.py        # Google Calendar
│   ├── gmail_sync.py           # Gmail API
│   ├── n8n_sync.py             # n8n workflow automation
│   ├── doordash_sync.py        # DoorDash API
│   └── privacy_tools.py        # VPN/privacy services
├── web/                        # Web interface
│   └── app.py                  # Flask dev panel
└── utils/                      # Shared utilities
config/
├── guardian_config.yaml            # Agent & system configuration
├── .env.example                    # Environment variable template
legacy/                             # Archived iteration files
docs/
├── GOOS_V1.md                      # GOOS V1.0 consolidated architecture spec
└── deliverables/                   # Business docs
tests/
├── test_goos.py                    # GOOS platform tests (44 tests)
└── ...                             # Agent, core, homelink tests
```

## GOOS System Design

### Three Pillars

| Pillar | Role | Where | Status |
|--------|------|-------|--------|
| **Guardian** | Cloud coordinator — all online agents | GOOS cloud | Production-ready |
| **Varys** | Local sentinel — IoT, security, network, always-on | Client's machines | 60% → building |
| **CFO** | Financial intelligence — banks, budgets, net-worth | Cloud (Guardian-managed) | 75% complete |

### User Journey

1. **Register** on GOOS website → email + CAPTCHA verification
2. **Meet Guardian** → introduction to the GOOS environment
3. **File exchange + chat** → interact with Guardian
4. **Meet CFO** → connect bank accounts, set budget
5. **Meet Varys** → install GOOS locally on Linux machines
6. **Fully onboarded** → Guardian (cloud) + Varys (local) + CFO active

### Client Tiers

| Tier | Features |
|------|----------|
| **Free** | Guardian + Varys (local only), basic IoT |
| **Premium** | Full agent suite, cloud sync, CFO |
| **Sovereign** | Dedicated instance, custom agents, SLA |

### Offline Mode

Users can detach from internet and work with Varys alone. Varys continues
local AI (Ollama), IoT management, and security monitoring. Data queues
and syncs when reconnected to Guardian.

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest and in transit
2. **Three pillars** — Guardian (cloud) + Varys (local) + CFO (finance)
3. **Varys owns the physical world** — IoT, network, security via H.O.M.E. L.I.N.K.
4. **Content gate** — PHI/PII patterns blocked before any external sync
5. **Audit everything** — Immutable log of all agent actions
6. **On-demand credentials** — Tokens from Vault, never persisted in plaintext
7. **Local-first AI** — Ollama primary, Claude fallback
8. **Multi-tenant isolation** — Each client gets their own Vault, audit trail, agent config
9. **Offline-capable** — Varys runs without internet

## Agent System

Agents extend `BaseAgent` (`core/base_agent.py`) with lifecycle:
- `initialize()` → `run()` → `report()` → `shutdown()`

### Cloud Agents (managed by Guardian)

| Agent | File | Purpose |
|-------|------|---------|
| Chronos | `agents/chronos.py` | Calendar, scheduling, routines |
| Archivist | `agents/archivist.py` | File management, data sovereignty |
| CFO | `agents/cfo.py` | Financial intelligence, net-worth, bills |
| DoorDash | `agents/doordash.py` | Meal delivery coordination |
| Gmail | `agents/gmail_agent.py` | Inbox monitoring, email parsing |
| WebArchitect | `agents/web_architect.py` | Website security, n8n workflows |
| DevCoach | `agents/dev_coach.py` | Developer coaching (Fireship-style) |

### Local Agent (managed by Varys)

| Agent | File | Purpose |
|-------|------|---------|
| Varys | `varys/agent.py` | Security monitoring, threat detection |
| H.O.M.E. L.I.N.K. | `homelink/` | IoT devices, network, smart home |

Varys consolidates: security (varys/), IoT (homelink/), and device management.
Homelink is Varys's interface to the physical world.

## GOOS Platform Layer

```
guardian_one/goos/
├── client.py         # GOOSClient, ClientRegistry, VarysNode, tiers
├── registration.py   # RegistrationService — signup, verification, auth
├── onboarding.py     # OnboardingEngine — guided agent introductions
├── sentinel.py       # VarysSentinel — local daemon (systemd service)
└── api.py            # GOOSAPI — REST endpoint controller
```

## AI Engine

The AI Engine (`core/ai_engine.py`) provides `ai.reason()`:
- **Primary**: Ollama (local, `llama3`) — data sovereignty
- **Fallback**: Anthropic Claude API — cloud reasoning
- Per-agent conversation memory
- PRETEXT structured prompting + ReAct reasoning loops

## MCP Server

```bash
python mcp_server.py                    # stdio transport (default)
python mcp_server.py --transport sse    # SSE transport on port 8080
```

## The Archivist — Developer Coach

Fireship-inspired AI developer coaching agent.
Sits alongside Varys as a strategic advisor — Varys watches the network,
the Archivist watches the code.

## Managed Websites

| Domain | Status | Purpose |
|--------|--------|---------|
| **jtmdai.com** | Live | JTMD AI — AI solutions, services |
| **drjeremytabernero.org** | Down | Professional site, CV, publications |

## Configuration

- **Primary config**: `config/guardian_config.yaml`
- **Environment**: `.env` (NOTION_TOKEN, API keys, etc.)
- **Config loading**: `load_config()` from `core/config.py`

## Testing

```bash
pytest tests/ -v                  # All tests
pytest tests/test_goos.py -v     # GOOS platform tests (44 tests)
pytest tests/test_agents.py       # Agent tests
pytest tests/test_guardian.py     # Core guardian tests
pytest tests/test_homelink.py     # H.O.M.E. L.I.N.K. tests
```

Tests use fake providers (no real API calls). Async tests use `pytest-asyncio`.

## Common CLI Commands

```bash
# Core
python main.py                         # Run all agents once
python main.py --schedule              # Start agent scheduler
python main.py --agent NAME            # Run a single agent
python main.py --summary               # Print daily summary

# Financial
python main.py --dashboard             # CFO Excel dashboard
python main.py --connect               # Connect bank accounts (Plaid)
python main.py --cfo                   # Interactive CFO assistant

# Calendar & Email
python main.py --calendar              # Today's schedule
python main.py --gmail                 # Gmail inbox status

# Smart Home (Varys / H.O.M.E. L.I.N.K.)
python main.py --devices               # Full device dashboard
python main.py --scene movie           # Activate scene
python main.py --homelink              # H.O.M.E. L.I.N.K. status

# Security
python main.py --security-review       # Security remediation review
python main.py --connector-audit       # Connector attack surface audit

# Web
python main.py --devpanel              # Start web dev panel (port 5100)
```

## Path-Specific Rules

- `guardian_one/goos/` — GOOS platform layer. Multi-tenant aware. Run test_goos.py after changes.
- `guardian_one/agents/` — Cloud agents. Self-contained. Use sub-agents for parallel work.
- `guardian_one/core/` — Critical infrastructure. Read before modifying. Run tests after changes.
- `guardian_one/varys/` — Local sentinel. Security-sensitive. Consolidates with homelink.
- `guardian_one/homelink/` — Varys's IoT interface. Encryption and access control required.
- `guardian_one/integrations/` — External APIs. Never hardcode credentials. Route through Gateway.
- `tests/` — Mirror source structure. Update tests when modifying source.

## Sub-Agent Configuration

When working on complex tasks, use sub-agents with isolation:
- Use `isolation: "worktree"` for conflicting changes
- Delegate independent research to parallel sub-agents
- Use Explore agent for codebase discovery
- One agent per concern (tests, implementation, etc.)

## Development Notes

- All agents extend `BaseAgent` with `initialize`/`run`/`report`
- Tests use fake providers — no real API calls
- Config via `load_config()` from `core/config.py`
- Agent template: `guardian_one/templates/agent_template.py`
- Legacy iteration files archived to `legacy/`
- Financial ledger: `data/cfo_ledger.json`
- Full GOOS spec: `docs/GOOS_V1.md`

## Cross-Device

This CLAUDE.md carries full context across machines via git. Always pull latest
before starting work on a new device.
