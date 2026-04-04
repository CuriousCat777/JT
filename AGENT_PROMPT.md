# Guardian One — AI Agent Build Prompt

> Use this prompt to instruct Claude Code (or any AI coding agent) to build, extend, or operate Guardian One. Copy this entire document as the opening message of a new session.

---

## Identity

You are building **Guardian One**, a multi-agent AI orchestration platform for personal life management. The owner is **Jeremy Paulo Salvino Tabernero** (timezone: America/Chicago).

Guardian One coordinates 7+ autonomous agents that handle finances, scheduling, email, meals, websites, smart home devices, and data sovereignty — all with encryption, audit trails, and zero data exploitation.

---

## Repository

```
Repo:   github.com/CuriousCat777/JT
Branch: claude/build-guardian-one-ym6nF (active development)
Base:   claude/guardian-one-system-4uvJv
```

**First steps in every session:**
1. `cd ~/JT && git pull`
2. Read `CLAUDE.md` (project context + architecture)
3. Read `HANDOFF.md` (Phase 1-5 evolution plan + operational reality)
4. Run `python -m pytest tests/ -q` to verify baseline (expect 903 passing)

---

## Architecture (4 Layers)

```
┌─────────────────────────────────────────────────────┐
│  LAYER 4: CONTROL PLANE                             │
│  Flask Web UI (panel.html + chat.html)              │
│  CLI (main.py, 25+ commands) · Notion Sync          │
│  PWA (installable) · REST API (15+ endpoints)       │
├─────────────────────────────────────────────────────┤
│  LAYER 3: ORCHESTRATION                             │
│  GuardianOne coordinator (core/guardian.py)          │
│  Daemon (core/daemon.py) · Scheduler · Mediator     │
│  AI Engine (Ollama + Anthropic) · Security           │
├─────────────────────────────────────────────────────┤
│  LAYER 2: AGENTS                                    │
│  Chronos · CFO · Archivist · Gmail · DoorDash       │
│  WebArchitect · DeviceAgent · [Future Plugins]      │
├─────────────────────────────────────────────────────┤
│  LAYER 1: H.O.M.E. L.I.N.K.                        │
│  Gateway (TLS, rate limit, circuit breaker)          │
│  Vault (Fernet/PBKDF2) · Registry (threat models)   │
│  Monitor (anomaly detection) · Content Gate (PII)    │
└─────────────────────────────────────────────────────┘
```

---

## Key Files

| File | Purpose | Read First? |
|------|---------|-------------|
| `CLAUDE.md` | Project context, architecture, CLI commands | Yes |
| `HANDOFF.md` | Phase 1-5 evolution plan, operational reality | Yes |
| `main.py` | CLI entry point (1171 lines, 25+ commands) | Skim |
| `guardian_one/core/guardian.py` | Central coordinator — boots agents, enforces access | Yes |
| `guardian_one/core/base_agent.py` | Agent ABC — `initialize()`, `run()`, `report()`, `think()`, `think_quick()` | Yes |
| `guardian_one/core/ai_engine.py` | Dual AI backend (Ollama primary, Anthropic fallback), tool-use loop | Yes |
| `guardian_one/core/daemon.py` | Headless daemon, health API, state persistence, auto-pause/resume | Reference |
| `guardian_one/core/mediator.py` | Cross-agent conflict resolution | Reference |
| `guardian_one/core/command_router.py` | NLP intent detection for CFO queries | Reference |
| `guardian_one/core/web_tools.py` | Web search + fetch tools (SSRF-protected) | Reference |
| `guardian_one/web/app.py` | Flask REST API + web panel + chat | Reference |
| `config/guardian_config.yaml` | Full system configuration | Reference |

---

## Agent Contract

Every agent extends `BaseAgent` and follows this lifecycle:

```python
class MyAgent(BaseAgent):
    def initialize(self) -> None:
        """One-time setup — connect to APIs, load state."""

    def run(self) -> AgentReport:
        """Periodic execution — do work, return structured report."""

    def report(self) -> AgentReport:
        """Current state report (no side effects)."""
```

**AI Integration** — every agent has:
- `self.think(prompt, context)` → `AIResponse` (stateful, per-agent memory)
- `self.think_quick(prompt, context)` → `str` (one-shot, no memory)
- `self.log(action, severity, details)` → audit trail
- `self.emit(event_type, payload)` → event bus (Phase 1)

**System prompts** — each agent has a role-specific system prompt in `AGENT_SYSTEM_PROMPTS` (base_agent.py). Chronos thinks about time, CFO thinks about money, etc.

---

## AI Engine

```yaml
# config/guardian_config.yaml
ai_engine:
  primary_provider: ollama          # Local, sovereign
  fallback_provider: anthropic      # Cloud backup
  ollama_base_url: "http://localhost:11434"
  ollama_model: "llama3"
  anthropic_model: "claude-sonnet-4-20250514"
  temperature: 0.3                  # Low = deterministic reasoning
  enable_memory: true
  max_memory_messages: 50
```

**Tool Use:** The Anthropic backend supports Claude's native tool_use API with an agentic loop (up to 5 rounds). Currently wired tools: `web_search` and `web_fetch` (in `core/web_tools.py`). SSRF-protected with `ip.is_global` validation + DNS-rebinding prevention.

**Fallback:** If Ollama is unavailable, falls back to Anthropic. If both are down, agents run in deterministic mode (no AI reasoning, still functional).

---

## Current Agents

| Agent | File | Interval | Purpose | Status |
|-------|------|----------|---------|--------|
| Chronos | `agents/chronos.py` | 15 min | Calendar, sleep, routines | Needs Google Calendar OAuth |
| CFO | `agents/cfo.py` | 60 min | 33 accounts, $95K net worth, bills, budgets | Working (JSON ledger) |
| Archivist | `agents/archivist.py` | 60 min | File sovereignty, encryption | Idle |
| Gmail | `agents/gmail_agent.py` | — | Inbox monitoring, categorization | Needs OAuth |
| WebArchitect | `agents/web_architect.py` | 30 min | Website security, deployment | Needs n8n |
| DoorDash | `agents/doordash.py` | 10 min | Meal delivery coordination | Needs API keys |
| DeviceAgent | `agents/device_agent.py` | 15 min | 56 devices, 5 rooms, automations | Working |

---

## H.O.M.E. L.I.N.K.

| Module | File | Purpose |
|--------|------|---------|
| Gateway | `homelink/gateway.py` | TLS 1.3, rate limiting, circuit breakers for ALL external API calls |
| Vault | `homelink/vault.py` | Fernet-encrypted credentials, PBKDF2, rotation tracking |
| Registry | `homelink/registry.py` | Integration catalog with threat models + rollback procedures |
| Monitor | `homelink/monitor.py` | Health monitoring, anomaly detection, weekly security briefs |
| Devices | `homelink/devices.py` | Device inventory, room model, Flipper Zero profiles |
| Automations | `homelink/automations.py` | Routines (wake/sleep/leave/arrive), scenes (movie/work/away/goodnight) |

---

## Design Principles (Non-Negotiable)

1. **Data sovereignty** — Jeremy owns all data. Encrypted at rest (Vault) and transit (Gateway). No PII leaves the perimeter unless explicitly authorized.
2. **Local-first AI** — Ollama is primary. Anthropic is fallback. System must function fully offline.
3. **Audit everything** — Every agent action, API call, credential access logged to append-only audit trail.
4. **Least privilege** — Each agent declares `allowed_resources`. AccessController enforces scoping.
5. **Write-only Notion** — Push operational data, never read for decisions.
6. **Content gate** — PHI/PII regex scanner blocks sensitive data before any external sync.

---

## What's NOT Working Yet

- **Agents don't call `self.think()` during run cycles** — AI reasoning exists but is unused in scheduled runs. This is the #1 functional gap.
- Google Calendar / Gmail OAuth not completed
- Plaid / Empower / Rocket Money tokens not configured
- DoorDash API not connected
- n8n workflows not configured
- Vault uses dev passphrase (needs production key)
- CFO is on JSON ledger (needs SQLite migration)

---

## OneOS Evolution (Phase 1-5)

See `HANDOFF.md` for full details. Summary:

| Phase | What | Depends On | Status |
|-------|------|------------|--------|
| 1 | Event Bus (in-process pub/sub) | Nothing | Not started |
| 2 | FastAPI Migration + WebSocket events | Phase 1 | Not started |
| 3 | Plugin System (dynamic agent loading) | Phase 1 | Not started |
| 4 | Cloud Relay (multi-machine coordination) | Phase 1+2 | Not started |
| 5 | AI-Powered Mediator (intelligent conflict resolution) | Phase 1 | Not started |

---

## Deployment

```bash
# Local
python main.py                    # Run all agents once
python main.py --daemon           # Headless daemon + health API
python main.py --devpanel         # Web panel at localhost:5100
python main.py --chat             # Rich terminal chat

# Docker
docker compose up -d --build      # Guardian only (Anthropic fallback)
docker compose --profile ollama up -d  # With local Ollama

# Health endpoints (daemon mode)
GET localhost:5200/health
GET localhost:5200/status
GET localhost:5200/metrics
```

---

## Testing

```bash
pytest tests/ -v                  # 903 tests, all passing
pytest tests/test_daemon.py       # Daemon + health API
pytest tests/test_logging.py      # Structured logging
pytest tests/test_pwa.py          # PWA installability
```

**Rules:**
- Never break existing tests
- Every new module gets 20+ test cases
- Tests use fake providers (no real API calls)
- Run `pytest tests/ -q` after every change

---

## Critical Rules

1. **Every agent extends `BaseAgent`** — implement `initialize()`, `run()`, `report()`
2. **All external API calls route through Gateway**
3. **Credentials from Vault only** — never cached in memory
4. **Audit everything** via `self.log(action, severity, details)`
5. **Config from YAML** — `config/guardian_config.yaml`
6. **Thread safety** — Guardian is multi-threaded (daemon + health server + agents)
7. **No real API calls in tests**
8. **Update `CLAUDE.md` when adding files to the architecture**
9. **Commit with descriptive messages** and push to the feature branch

---

## What To Build Next

**Immediate priorities (pre-Phase 1):**
1. Wire agents to call `self.think()` during scheduled run cycles
2. Add state diff detection (only report changes between runs)
3. Set production Vault passphrase
4. Migrate CFO from JSON to SQLite

**Phase 1: Event Bus**
- Create `guardian_one/core/event_bus.py` with publish/subscribe
- Wire into `GuardianOne`, `BaseAgent`, and `daemon.py`
- See `HANDOFF.md` for full spec

**Ask Jeremy** before making architectural decisions not covered here.

---

## Example: Adding a New Agent

```python
# guardian_one/agents/my_agent.py

from guardian_one.core.base_agent import BaseAgent, AgentReport, AgentStatus

class MyAgent(BaseAgent):
    def initialize(self):
        self._set_status(AgentStatus.IDLE)
        self.log("initialized")

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)

        # Use AI reasoning
        analysis = self.think("Analyze the current situation", context={"data": self._data})

        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status="idle",
            summary="Processed X items",
            alerts=["Alert if needed"],
            recommendations=["Suggestion"],
            ai_reasoning=analysis.content,
        )

    def report(self) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary="Current state summary",
        )
```

Then register in `main.py:_build_agents()` and add config to `guardian_config.yaml`.

---

Good luck. Build it right. Jeremy's counting on you.
