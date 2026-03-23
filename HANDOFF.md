# Guardian One — Project Handoff

**Date:** 2026-03-23
**Owner:** Jeremy Paulo Salvino Tabernero
**Repo:** ~/JT (git)
**Branch with latest work:** `claude/guardian-one-system-4uvJv`

---

## What This Is

Guardian One is a multi-agent AI system for personal life management. It's built in Python and runs locally. It manages finances, scheduling, email, smart home devices, websites, and security — all with encrypted credentials, audit trails, and zero cloud data exploitation.

## Current State: What Actually Works

### The Guardian boots and runs all 7 agents
```bash
python main.py              # Run all agents, print daily summary
python main.py --chat       # CLI chat interface with Guardian
python main.py --devpanel   # Web UI at http://localhost:5100
                            # Chat at http://localhost:5100/chat
```

### Agents registered and functional at boot:
| Agent | Status | What It Does |
|-------|--------|-------------|
| **chronos** | Idle, needs calendar OAuth | Schedule & calendar management |
| **archivist** | Idle | File & data sovereignty tracking |
| **cfo** | Working | Financial intelligence — 33 accounts, net worth $95K, overdue bill detection, budget tracking, spending analysis, tax recommendations, home purchase scenarios |
| **doordash** | Idle, needs API keys | Meal delivery coordination |
| **gmail** | Idle, needs OAuth2 | Email & inbox monitoring |
| **web_architect** | Idle, needs n8n | Website management for drjeremytabernero.org and jtmdai.com |
| **device_agent** | Working | Smart home: 9 devices, 5 rooms, 11 automation rules, 4 scenes, Flipper Zero profiles |

### Chat Interface (web + CLI)
Both `/chat` (web) and `--chat` (CLI) support these commands:
- `status` — full system dump
- `agents` — list all agents and their state
- `agent <name>` — run a specific agent
- `brief` — weekly H.O.M.E. L.I.N.K. brief
- `devices` / `rooms` / `audit` — smart home
- `scene movie|work|away|goodnight` — activate home scenes
- `event wake|sleep|leave|arrive` — fire daily routines
- `homelink` — API service status
- `reviews` — items needing Jeremy's review
- `cfo <question>` — natural language financial queries (keyword-based, works without AI)
- `think <question>` — AI-powered reasoning (needs Ollama or Anthropic)

Web chat has a **toggle**: LOCAL (deterministic, works now) vs AI (needs Ollama/Anthropic).

### H.O.M.E. L.I.N.K. — Two systems in one:
1. **API Infrastructure**: Gateway (TLS, rate limiting, circuit breakers), Vault (Fernet-encrypted credentials), Registry (threat models per integration), Monitor (anomaly detection, weekly briefs)
2. **Smart Home Control**: Device inventory (cameras, Samsung TV, plugs, lights, blinds, Flipper Zero, vehicle), room model, automation engine (wake/sleep/leave/arrive routines, sunrise/sunset triggers, occupancy detection, named scenes)

### Tests
- **710 tests pass**, 2 collection errors (test_ollama_sync, test_scheduler — pre-existing), 1 pre-existing failure (AI engine error handling test)
- Run: `pytest tests/ -q --ignore=tests/test_ollama_sync.py --ignore=tests/test_scheduler.py`

### CFO Financial Data (real)
Jeremy's actual financial picture is in `data/cfo_ledger.json`:
- Net worth: $95,162.01
- 33 accounts across checking, savings, retirement, credit cards, loans
- 2 overdue bills (Capital One Platinum $221.94, Capital One VentureOne $3,140.04)
- Retirement: $157,665.58 (Essentia Health 457b, Roth IRA, Fidelity 401k)
- Student loans: ~$73K

---

## What Does NOT Work Yet

### AI Engine
- `guardian_one/core/ai_engine.py` exists with Ollama + Anthropic provider support
- **Ollama**: Configured for `llama3` at `localhost:11434`. Works on Jeremy's ROG X machine when Ollama is running. Not available in cloud/CI environments.
- **Anthropic**: Needs `ANTHROPIC_API_KEY` in `.env`. Not configured.
- The `think` command and AI-enhanced CFO responses depend on one of these being live.

### External Integrations (all need API keys in `.env`)
```
DOORDASH_DEVELOPER_ID, DOORDASH_KEY_ID, DOORDASH_SIGNING_SECRET  — DoorDash
ROCKET_MONEY_API_KEY                                              — Rocket Money
EMPOWER_API_KEY                                                   — Empower
PLAID_CLIENT_ID, PLAID_SECRET                                     — Plaid
NOTION_TOKEN                                                      — Notion
N8N_BASE_URL, N8N_API_KEY                                         — n8n
google_credentials.json in config/                                — Gmail + Calendar OAuth2
```

### Gmail & Calendar
- OAuth2 flow exists but needs `google_credentials.json` placed in `config/` and interactive browser auth.

### Websites
- WebArchitect manages drjeremytabernero.org and jtmdai.com
- Needs n8n credentials to actually build/deploy
- Notion website sync exists but needs NOTION_TOKEN

### Smart Home Devices
- All 9 devices registered but status is UNKNOWN (no actual network scanning)
- 28 security issues flagged (default passwords, firmware unknown, etc.)
- Automations defined but no real device control — actions are logged but not executed against real hardware
- Would need python-kasa (TP-Link), phue (Hue), etc. to actually control devices

### Scheduling / Daemon
- `Scheduler` class exists but `--schedule` needs testing
- No systemd service, cron job, or Task Scheduler integration yet
- No automatic morning briefing email

---

## Architecture (accurate as of this handoff)

```
main.py                              # CLI entry point (1300+ lines, 30+ commands)
guardian_one/
├── agents/
│   ├── chronos.py                   # Schedule & calendar
│   ├── archivist.py                 # File & data sovereignty
│   ├── cfo.py                       # Financial intelligence (WORKING)
│   ├── cfo_dashboard.py             # Excel financial dashboards
│   ├── doordash.py                  # Meal delivery
│   ├── gmail_agent.py               # Email monitoring
│   ├── web_architect.py             # Website management
│   ├── website_manager.py           # Per-site build/deploy
│   └── device_agent.py              # Smart home (WORKING)
├── core/
│   ├── guardian.py                   # Central coordinator (WORKING)
│   ├── base_agent.py                # Agent contract (ABC)
│   ├── ai_engine.py                 # Ollama + Anthropic reasoning
│   ├── command_router.py            # CFO natural language router
│   ├── mediator.py                  # Cross-agent conflict resolution
│   ├── scheduler.py                 # Agent scheduling
│   ├── sandbox.py                   # Deployment testing
│   ├── evaluator.py                 # Performance metrics
│   ├── audit.py                     # Immutable audit logging (WORKING)
│   ├── security.py                  # Access control (WORKING)
│   ├── security_remediation.py      # Security review system
│   └── config.py                    # Configuration management (WORKING)
├── homelink/                        # API infra + smart home control
│   ├── gateway.py                   # API gateway (WORKING)
│   ├── vault.py                     # Encrypted credentials (WORKING)
│   ├── registry.py                  # Integration catalog (WORKING)
│   ├── monitor.py                   # Health monitoring (WORKING)
│   ├── devices.py                   # Device inventory (WORKING)
│   └── automations.py               # Automation engine (WORKING)
├── integrations/                    # External service connectors (all need API keys)
├── web/
│   ├── app.py                       # Flask web UI + chat API (WORKING)
│   └── templates/
│       ├── panel.html               # Dev panel dashboard
│       └── chat.html                # Chat interface (WORKING)
└── utils/
config/
├── guardian_config.yaml             # Agent & system configuration
data/
├── cfo_ledger.json                  # Jeremy's real financial data
tests/                               # 710 passing tests
```

## Key Files to Read First
1. `CLAUDE.md` — project context (updated this session)
2. `main.py` — all CLI commands and agent registration
3. `guardian_one/core/guardian.py` — the coordinator
4. `guardian_one/web/app.py` — web UI + chat API
5. `config/guardian_config.yaml` — system configuration

## Dependencies
```
pip install python-dotenv flask cryptography cffi pyyaml openpyxl
```
Full list in `requirements.txt` and `pyproject.toml`.

## What Needs to Happen Next (Priority Order)

1. **Get Ollama running** — Jeremy has a ROG X with 64GB RAM. Install Ollama, pull mistral or llama3, set `OLLAMA_BASE_URL` in `.env`. The AI `think` command and enhanced CFO responses will light up immediately.

2. **Wire real device control** — `pip install python-kasa` for TP-Link plugs, `phue` for Hue bridge. The automation rules and scenes are defined — they just need real device drivers behind the actions.

3. **Set up Gmail/Calendar OAuth** — Drop `google_credentials.json` in `config/`, run interactive auth once. Chronos and Gmail agents will activate.

4. **Daemon/scheduler** — Make Guardian run daily checks automatically. Options: systemd service, cron, or Windows Task Scheduler on the ROG X.

5. **Morning briefing email** — The daily summary and weekly brief exist as text. Wire to `notifications.py` (exists in utils) to email Jeremy each morning.

6. **Connect financial APIs** — Plaid for bank accounts (read-only), Rocket Money for aggregation. CFO is the most complete agent and will benefit most from live data.

---

## Known Issues

- `tests/test_ollama_sync.py` and `tests/test_scheduler.py` fail to collect (import issues)
- `tests/test_ai_engine.py::test_ollama_generate_returns_empty_on_error` fails (pre-existing)
- The `cryptography` package requires `cffi` to be installed (`pip install cffi`)
- Web dev panel (`panel.html`) exists but is the old dashboard — `/chat` is the new primary interface
- `data/cfo_ledger.json` contains real financial data — do not commit to public repos

## Session History (This Session — 2026-03-23)

1. Fixed broken `cryptography` dependency (missing `cffi`)
2. Gave H.O.M.E. L.I.N.K. its full identity — updated `__init__.py`, CLAUDE.md, monitor.py
3. Wired DeviceAgent into boot sequence (was only created on-demand)
4. Built CLI chat interface (`--chat`) routing to all agents
5. Built web chat interface (`/chat`) with AI/local toggle
6. Updated Guardian daily summary to include devices, rooms, automations
7. Updated Monitor weekly brief to include device health + automation status
8. Fixed test broken by monitor header text change
