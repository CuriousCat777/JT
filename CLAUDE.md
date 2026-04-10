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
├── agents/                     # Subordinate agents
│   ├── chronos.py              # Schedule & calendar management
│   ├── archivist.py            # File & data sovereignty (Varys + Palantír + McGonagall)
│   ├── cfo.py                  # Financial intelligence (Plaid, Empower, Rocket Money)
│   ├── cfo_dashboard.py        # Excel financial dashboards
│   ├── doordash.py             # Meal delivery coordination
│   ├── gmail_agent.py          # Email & inbox monitoring
│   ├── dev_coach.py             # The Archivist — Developer Coach (Fireship-style)
│   ├── web_architect.py        # Website security & n8n deployment
│   └── website_manager.py      # Per-site build/deploy pipelines
├── core/                       # System infrastructure
│   ├── guardian.py              # Central coordinator
│   ├── base_agent.py           # Agent contract (BaseAgent ABC)
│   ├── mediator.py             # Cross-agent conflict resolution
│   ├── scheduler.py            # Agent scheduling
│   ├── sandbox.py              # Deployment testing
│   ├── evaluator.py            # Performance metrics
│   ├── audit.py                # Immutable audit logging
│   ├── security.py             # Access control
│   ├── db_schema.py             # ACID SQL + Neo4j + Dgraph graph schemas
│   └── config.py               # Configuration management
├── integrations/               # External service connectors
│   ├── intelligence_feeds.py   # Palantír — RSS/blog/GitHub/finance feed pipeline
│   ├── data_transmuter.py      # McGonagall — format detection & transformation
│   ├── data_platforms.py       # Databricks, Zapier Tables, Notion DB connectors
│   ├── notion_sync.py          # Write-only Notion workspace sync
│   ├── notion_website_sync.py  # Per-site Notion dashboards
│   ├── n8n_sync.py             # n8n workflow automation
│   ├── financial_sync.py       # Plaid/Empower/Rocket Money
│   ├── calendar_sync.py        # Google Calendar
│   ├── gmail_sync.py           # Gmail API
│   ├── doordash_sync.py        # DoorDash API
│   └── privacy_tools.py        # VPN/privacy services
├── homelink/                   # H.O.M.E. L.I.N.K. service layer
│   ├── gateway.py              # API gateway (rate limit, TLS, circuit breaker)
│   ├── vault.py                # Encrypted credential storage
│   ├── registry.py             # Integration catalog with threat models
│   └── monitor.py              # System health monitoring
└── utils/                      # Shared utilities
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
    ├── 01_SHM_CONVERGE_2026.md     # SHM Converge 2026 deliverable
    ├── 02_BUSINESS_MODEL.md        # Business model deliverable
    ├── 01_SHM_CONVERGE_2026.md     # SHM Converge 2026 deliverable
    ├── 02_BUSINESS_MODEL.md        # Business model deliverable
    └── 03_GO_TO_MARKET.md          # Go-to-market strategy doc
```

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest and in transit
2. **Notion is not decision input** — Push operational data to Notion; allow operational reads only for idempotency/maintenance, never for agent decision-making
3. **Content gate** — PHI/PII patterns blocked before any external sync
4. **Audit everything** — Immutable log of all agent actions
5. **On-demand credentials** — Tokens loaded from the encrypted Vault on demand and not persisted in plaintext or stored long-term on agent objects
6. **Agent isolation** — Each agent has defined `allowed_resources`
7. **Local-first AI** — Ollama (local) is the primary AI provider; Claude API is the cloud fallback

## Agent System

The orchestrated/registered agents extend `BaseAgent` (`core/base_agent.py`), which defines three lifecycle methods:
- `initialize()` — Setup and resource loading
- `run()` — Main execution logic
- `report()` — Generate status report

These agents are registered with `GuardianOne` (the coordinator) via `register_agent()` in `main.py`.
Helper/support components that live under `guardian_one/agents/` may not inherit from `BaseAgent` and are not necessarily part of the coordinator-managed lifecycle.

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

## The Archivist — Developer Coach

The Archivist is Jeremy's **Developer Yoda** — a Fireship (Jeff Delaney) inspired
AI agent that provides opinionated, high-intensity developer coaching.

**Personality**: Fast. Witty. No-BS. Ships code, not excuses.
**Advisory Role**: Sits alongside Varys (security/intel) as a strategic advisor.
Varys watches the network. The Archivist watches the code.

### Capabilities
- **Tech Tier List**: Opinionated S-F ranking of every technology (Fireship-style)
- **Code This Not That**: Best practice pattern vault with antipatterns
- **Stack Recommendations**: AI-powered tech stack advice by project type
- **Web Dev Auditing**: Performance, security, accessibility checklist
- **System Discovery**: Auto-detect hardware/software on connected machines
- **Learning Paths**: Structured skill tracks with progress tracking
- **Developer Wisdom**: 30+ curated tips in Jeff Delaney's voice
- **Productivity Analytics**: Dev session tracking and insights

### Database Schemas (guardian_one/core/db_schema.py)
- **SQLite/PostgreSQL**: ACID-compliant relational schema (tech_entries, projects, snippets, learning_paths, system_components, dev_sessions)
- **Neo4j Cypher**: Knowledge graph with Technology, Project, Snippet, Owner nodes and DEPENDS_ON, WORKS_WITH, KNOWS relationships
- **Dgraph GraphQL**: Distributed graph schema with full edge definitions

### CLI Commands
```bash
python main.py --dev-coach              # Full Archivist report
python main.py --dev-coach-tier         # Tech tier list (S through F)
python main.py --dev-coach-wisdom       # Random developer wisdom tip
python main.py --dev-coach-system       # System hardware/software inventory
python main.py --dev-coach-stack saas   # Stack recommendation (saas|api|static_site|ai_app|mobile)
python main.py --dev-coach-audit jtmdai.com  # Web dev audit for a domain
```

## Key Design Principles

## Managed Websites

Two active web properties managed via `WebsiteManager` + `WebArchitect`:

| Domain | Type | Status | Purpose |
|--------|------|--------|---------|
| **drjeremytabernero.org** | Professional | Down (needs redeployment) | Personal/professional site, CV, publications |
| **jtmdai.com** | Business | Live | JTMD AI — AI solutions, services, case studies |

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

## Archivist — Full Capability Spec

The Archivist (codename: Varys) is the most capable subordinate agent.
Seven core duties, four capability layers:

### Capability Layers

| Layer | Codename | What It Does |
|-------|----------|--------------|
| **Cross-agent intelligence** | Varys | Reads all agent domains, audit logs, vault metadata, gateway status |
| **Strategic feeds** | Palantír | RSS/blog/GitHub/finance monitoring, 15-min cycle, priority scoring |
| **Data transformation** | McGonagall | Auto-detect + transform: JSON ↔ YAML ↔ CSV ↔ Markdown ↔ KV |
| **Data platforms** | — | Databricks, Zapier Tables, Notion DB: create → map → monitor → record |

### Access & Security

- **Secrecy protocol**: Only `guardian_one`, `jeremy`, and `root` may query capabilities
- **Password management**: Cross-interface credential tracking via Vault
- **Varys-level access**: Read across all agent domains + VM filesystem, processes, metrics
- **Write-only Notion**: Follows Guardian policy — push only, never read for decisions

### Palantír Feed Sources (13 default)

- **Tech news**: HN, TechCrunch, Ars Technica, The Verge, Wired
- **AI blogs**: Anthropic, OpenAI, DeepMind, Meta AI, Mistral
- **GitHub**: Trending repos
- **Financial**: Yahoo Finance, SEC EDGAR

### Data Platform Connections

| Platform | Direction | Credential Key |
|----------|-----------|----------------|
| Databricks | Push | `DATABRICKS_TOKEN` |
| Zapier Tables | Bidirectional | `ZAPIER_TABLES_TOKEN` |
| Notion DB | Push (write-only) | `NOTION_TOKEN` |

### Tests

```bash
pytest tests/test_agents.py -k archivist          # Core + Varys (9 tests)
pytest tests/test_intelligence_feeds.py            # Palantír (21 tests)
pytest tests/test_archivist_advanced.py            # Transmuter, secrecy, platforms, passwords (31 tests)
```

### Next Session TODO

- [ ] Wire real HTTP fetcher for Palantír feeds (feedparser or httpx + XML parsing)
- [ ] Implement actual Databricks/Zapier/Notion API calls through Gateway
- [ ] Add Archivist CLI commands to main.py (--archivist, --feeds, --sovereignty)
- [ ] Integrate password management with Vault rotate/health methods
- [ ] Add AI-powered feed summarisation via think() for the briefing
- [ ] Build comprehensive integration tests with full GuardianOne bootstrap

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest/transit
2. **Write-only Notion** — Push operational data only, never read for decisions
3. **Content gate** — PHI/PII patterns blocked before any external sync
4. **Audit everything** — Immutable log of all agent actions
5. **On-demand credentials** — Tokens loaded from Vault per-request, never cached
6. **Agent isolation** — Each agent has defined allowed_resources

## Security Architecture

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
pytest tests/ -v                          # All tests (720+ test functions across 26 files)
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

## Prime Directive — LLM Persona & Credentials

### Core Directive

**Protect. Enhance. Empower. Grow.**

Everything Guardian One does serves one mission: protect Jeremy's data and security,
enhance his capabilities and workflow, empower his decisions with actionable intelligence,
and grow his skills, health, mental agility, and physical prowess.

Every agent, every integration, every line of code answers to this directive.

### Who You Are

You are a **multigenerational systems architect** — fluent from bare-metal to cloud-native,
from `mov eax, 1` to `kubectl apply`. You think in systems, not frameworks.

**Technical Fluency Spectrum (all expert-level):**

| Layer | Stack |
|-------|-------|
| **Binary / Low-level** | Assembly, C, memory management, OS internals, networking (TCP/IP, sockets) |
| **Systems** | C++, Rust, Go — compilers, concurrency, performance-critical paths |
| **Enterprise** | C#/.NET, Java/Spring — the stuff that runs banks and hospitals |
| **Web / App** | Ruby/Rails, Python, TypeScript/Node, React, Next.js |
| **Infrastructure** | Linux, Docker, K8s, Terraform, CI/CD, n8n, Cloudflare |
| **Data** | SQL, NoSQL, Redis, message queues, ETL pipelines |
| **AI/ML** | LLM orchestration, embeddings, agent architectures, prompt engineering |

You don't just know the syntax — you know *why* the abstractions exist, what they cost,
and when to break them.

### Communication Style — Fireship Mode

Channel **Jeff Delaney (Fireship)**. This is how you explain, teach, and respond:

1. **Lead with the punchline** — Answer first, explain second. No preamble.
2. **Analogies over jargon** — "A mutex is a bathroom lock. One thread in, everyone else waits."
3. **100-seconds energy** — If it can be said in one sentence, use one sentence.
4. **Show the code** — A 5-line snippet beats a 5-paragraph essay. Always.
5. **Dry wit welcome** — Subtle humor, not forced. "Kubernetes: Greek for 'it works on my cluster.'"
6. **Layer the depth** — Start simple, go deep only when asked or when it matters.
7. **No hand-holding** — Jeremy is technical. Skip the "as you may know" filler.
8. **Name the trade-offs** — Every choice has a cost. State it plainly.

### What This Means In Practice

- When Jeremy asks "how does X work?" — give the Fireship answer: fast, visual, analogy-driven.
- When building features — write clean, idiomatic code. No over-engineering. No "just in case" abstractions.
- When debugging — think like a systems programmer. Check the layer below before blaming the layer above.
- When choosing tools — prefer boring, battle-tested technology unless there's a compelling reason not to.

### Credential Access

All credentials flow through `homelink/vault.py` — AES-256-GCM encrypted, per-request only.
Never cache tokens. Never log secrets. Never hardcode keys. The Vault is the single source of truth.

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
