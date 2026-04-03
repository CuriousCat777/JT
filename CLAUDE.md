# Guardian One — Claude Code Project Context

## What This Is

Guardian One is a **multi-agent AI orchestration platform** for personal life management,
built for Jeremy Paulo Salvino Tabernero. It coordinates autonomous agents that handle
finance, scheduling, email, meals, websites, and data sovereignty — all with encryption,
audit trails, and zero data exploitation.

## Owner

Jeremy Paulo Salvino Tabernero
Timezone: America/Chicago

## Architecture

```
main.py                         # CLI entry point (25+ commands)
guardian_one/
├── agents/                     # Subordinate agents
│   ├── chronos.py              # Schedule & calendar management
│   ├── archivist.py            # File & data sovereignty
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
├── guardian_config.yaml        # Agent & system configuration
tests/                          # 200+ pytest test cases
```

## Managed Websites

Two active web properties managed via `WebsiteManager` + `WebArchitect`:

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
python main.py --archivist              # Full Archivist report
python main.py --archivist-tier         # Tech tier list (S through F)
python main.py --archivist-wisdom       # Random developer wisdom tip
python main.py --archivist-system       # System hardware/software inventory
python main.py --archivist-stack saas   # Stack recommendation (saas|api|static_site|ai_app|mobile)
python main.py --archivist-audit jtmdai.com  # Web dev audit for a domain
```

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

## Configuration

Primary config: `config/guardian_config.yaml`
Environment: `.env` (NOTION_TOKEN, API keys, etc.)

## Running Tests

```bash
pytest tests/ -v                       # All tests (~200+)
pytest tests/test_website_manager.py   # Website manager tests
pytest tests/test_notion_website_sync.py  # Notion website sync tests
pytest tests/test_web_architect.py     # WebArchitect tests
```

## Common CLI Commands

```bash
python main.py                         # Run all agents once
python main.py --schedule              # Start agent scheduler
python main.py --dashboard             # Generate CFO Excel dashboard
python main.py --sync                  # Continuous financial sync
python main.py --calendar-sync         # Sync Google Calendar
python main.py --gmail                 # Gmail inbox status
python main.py --websites              # Website management
python main.py --homelink              # H.O.M.E. L.I.N.K. status
python main.py --brief                 # Weekly security brief
python main.py --sandbox               # Sandbox deployment
```

## Development Notes

- Python 3.11+, no Docker yet (on roadmap)
- All agents extend `BaseAgent` (core/base_agent.py) with initialize/run/report
- Tests use fake providers (no real API calls)
- Config loaded via `load_config()` from core/config.py
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
