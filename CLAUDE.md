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
│   ├── archivist.py            # Central telemetry & data sovereignty
│   ├── cfo.py                  # Financial intelligence (Plaid, Empower, Rocket Money)
│   ├── cfo_dashboard.py        # Excel financial dashboards
│   ├── device_agent.py         # Smart home, IoT, network security
│   ├── doordash.py             # Meal delivery coordination
│   ├── gmail_agent.py          # Email & inbox monitoring
│   ├── web_architect.py        # Website security & n8n deployment
│   └── website_manager.py      # Per-site build/deploy pipelines
├── archivist/                  # Archivist subsystems (central nervous system)
│   ├── telemetry.py            # TelemetryHub — cross-system JSONL event logging
│   ├── techdetect.py           # TechDetector — auto-detect new tech/services
│   ├── cloudsync.py            # CloudSync — multi-cloud backup portals
│   ├── file_organizer.py       # FileOrganizer — auto-categorize files, cleanup
│   ├── account_manager.py      # AccountManager — unified account/storage tracker
│   ├── password_sync.py        # PasswordSync — 1Password/Bitwarden CLI integration
│   └── knowledge_export.py     # KnowledgeExporter — RAG docs for Open WebUI
├── varys/                      # VARYS — Cybersecurity SIEM agent
│   ├── engine.py               # VarysEngine — monitoring loop coordinator
│   ├── models.py               # SecurityEvent, Alert, Incident models
│   ├── sigma/                  # Detection rules (Sigma-compatible)
│   ├── ingestion/              # Event collectors (Wazuh, syslog, auth)
│   ├── detection/              # Anomaly detection, entity scoring
│   ├── response/               # SOAR-lite automated response actions
│   └── api/                    # Flask Blueprint REST API
├── core/                       # System infrastructure
│   ├── guardian.py              # Central coordinator
│   ├── base_agent.py           # Agent contract (BaseAgent ABC)
│   ├── daemon.py               # Daemon mode with health API
│   ├── ai_engine.py            # Multi-provider AI (Ollama, Anthropic, Cloudflare)
│   ├── mediator.py             # Cross-agent conflict resolution
│   ├── scheduler.py            # Agent scheduling
│   ├── sandbox.py              # Deployment testing
│   ├── evaluator.py            # Performance metrics
│   ├── audit.py                # Immutable audit logging
│   ├── security.py             # Access control
│   └── config.py               # Configuration management
├── integrations/               # External service connectors (12 modules)
│   ├── notion_sync.py          # Write-only Notion workspace sync
│   ├── notion_website_sync.py  # Per-site Notion dashboards
│   ├── n8n_sync.py             # n8n workflow automation
│   ├── financial_sync.py       # Plaid/Empower/Rocket Money
│   ├── calendar_sync.py        # Google Calendar
│   ├── gmail_sync.py           # Gmail API
│   ├── doordash_sync.py        # DoorDash API
│   ├── ollama_sync.py          # Local Ollama LLM integration
│   ├── plaid_connect.py        # Plaid financial data connector
│   ├── ring_monitor.py         # Ring doorbell/camera monitoring
│   └── privacy_tools.py        # VPN/privacy services
├── homelink/                   # H.O.M.E. L.I.N.K. service layer
│   ├── gateway.py              # API gateway (rate limit, TLS, circuit breaker)
│   ├── vault.py                # Encrypted credential storage (Fernet/PBKDF2-480K)
│   ├── registry.py             # Integration catalog with threat models
│   └── monitor.py              # System health monitoring
├── web/                        # DevPanel web dashboard
│   └── app.py                  # Flask app with OpenAI-compatible API
└── utils/                      # Shared utilities
config/
├── guardian_config.yaml        # Agent & system configuration
Dockerfile                      # Python 3.11-slim container
docker-compose.yml              # Guardian + Ollama + Open WebUI + (Wazuh)
.mcp.json                       # MCP server configuration
tests/                          # 913+ pytest test cases
```

## Key Architecture Notes

### Archivist = Central Telemetry System
The Archivist is NOT just a file manager — it is the **central nervous system** that
remembers, logs, and protects all data across every system. It contains:
- **TelemetryHub**: every interaction across every service feeds into one JSONL stream
- **TechDetector**: auto-detect new technology/services entering the ecosystem
- **CloudSync**: multi-cloud backup portals (local, Cloudflare R2, GitHub)
- **FileOrganizer**: auto-categorize files into taxonomy with cleanup rules
- **AccountManager**: unified account/storage tracker with password health scoring
- **PasswordSync**: 1Password/Bitwarden CLI metadata auditing (no secrets stored)
- **KnowledgeExporter**: converts state into Markdown for Open WebUI RAG

### VARYS = Cybersecurity Agent
Full SIEM pipeline: ingestion → detection (Sigma rules + anomaly) → scoring → response.
Safety rule: only ALERT auto-executes; all containment actions require human approval.

### AI Engine = Multi-Provider
Ollama (local) → Anthropic Claude (cloud) → Cloudflare Workers AI (edge).
Per-agent conversation memory with sliding window.

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest/transit
2. **Write-only Notion** — Push operational data only, never read for decisions
3. **Content gate** — PHI/PII patterns blocked before any external sync
4. **Audit everything** — Immutable log of all agent actions
5. **On-demand credentials** — Tokens loaded from Vault per-request, never cached
6. **Agent isolation** — Each agent has defined allowed_resources

## Security Architecture

- **Vault**: Fernet encryption with PBKDF2-SHA256 (480K iterations), per-credential scoping
- **Gateway**: TLS 1.2+ enforcement, rate limiting, circuit breakers for all external calls
- **Registry**: Every integration has a threat model (top 5 risks) and rollback procedure
- **Content Classification**: Regex-based PHI/PII scanner blocks sensitive data from sync
- **Audit Log**: Thread-safe, append-only JSONL with rotation, severity-tagged
- **Daemon Health API**: Binds 127.0.0.1 only (not 0.0.0.0)

## Python Patterns (IMPORTANT)

- **Signal handling**: Always wrap `signal.signal()` with
  `if threading.current_thread() is threading.main_thread()` to avoid errors in tests
- **Runtime data files**: Add to `.gitignore` BEFORE committing. Never commit runtime
  artifacts (telemetry.jsonl, state files, caches, etc.)
- **Test-driven**: Run full suite (`pytest tests/ -x -q`) before every push.
  Current count: 913+ tests passing.

## Running Tests

```bash
pytest tests/ -v                       # All tests (913+)
pytest tests/ -x -q --tb=short        # Fast fail mode
pytest tests/test_archivist_v2.py      # Archivist subsystems (30 tests)
pytest tests/test_varys.py             # VARYS agent + API tests
pytest tests/test_daemon.py            # Daemon + health API tests
```

## Docker Deployment

```bash
docker-compose up -d                   # Start Guardian + Ollama + Open WebUI
docker exec -it guardian-ollama ollama pull llama3  # Pull a model
# Open WebUI at http://localhost:3000
# Guardian health at http://localhost:8080/health
```

## Common CLI Commands

```bash
python main.py                         # Run all agents once
python main.py --schedule              # Start agent scheduler
python main.py --daemon                # Daemon mode with health API
python main.py --dashboard             # Generate CFO Excel dashboard
python main.py --sync                  # Continuous financial sync
python main.py --calendar-sync         # Sync Google Calendar
python main.py --gmail                 # Gmail inbox status
python main.py --websites              # Website management
python main.py --homelink              # H.O.M.E. L.I.N.K. status
python main.py --brief                 # Weekly security brief
python main.py --sandbox               # Sandbox deployment
```

## Managed Websites

| Domain | Type | Purpose |
|--------|------|---------|
| **drjeremytabernero.org** | Professional | Personal/professional site, CV, publications |
| **jtmdai.com** | Business | JTMD AI — AI solutions, services, case studies |

## Configuration

Primary config: `config/guardian_config.yaml`
Environment: `.env` (NOTION_TOKEN, API keys, etc.)

## Development Notes

- Python 3.11+, Docker available via docker-compose.yml
- All agents extend `BaseAgent` (core/base_agent.py) with initialize/run/report
- Tests use fake providers (no real API calls)
- Config loaded via `load_config()` from core/config.py
- Multi-device: This CLAUDE.md carries full context across machines via git
- GitHub repo: CuriousCat777/JT

## Cross-Device Setup

Clone on any machine and Claude Code will understand the project:
```bash
git clone <repo-url> ~/JT
cd ~/JT
# Claude Code reads this CLAUDE.md automatically
```

Both machines (current + ROG X 64GB) share context through this repo.
Always pull latest before starting work on a new device.
