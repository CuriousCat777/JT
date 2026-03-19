# Session Handoff: Guardian Core (Central Coordinator)

> Last updated: 2026-03-19
> Branch: `claude/guardian-one-system-4uvJv`

---

## What This Session Covers

You are working on **Guardian One's core orchestrator** — the central coordinator
that boots, supervises, and manages all subordinate agents. This includes the
agent lifecycle, AI engine, mediator, scheduler, audit, security, and CLI.

---

## System State Summary

### What's Solid

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| **GuardianOne coordinator** | `guardian_one/core/guardian.py` | 399 | Production-ready |
| **BaseAgent contract** | `guardian_one/core/base_agent.py` | 242 | Production-ready |
| **AI Engine (Ollama + Claude)** | `guardian_one/core/ai_engine.py` | 484 | Production-ready |
| **Audit logging** | `guardian_one/core/audit.py` | — | Production-ready |
| **Access control** | `guardian_one/core/security.py` | — | Production-ready |
| **Config management** | `guardian_one/core/config.py` | — | Production-ready |
| **Interactive scheduler** | `guardian_one/core/scheduler.py` | 314 | Production-ready |
| **H.O.M.E. L.I.N.K. (Gateway)** | `guardian_one/homelink/gateway.py` | — | Production-ready |
| **H.O.M.E. L.I.N.K. (Vault)** | `guardian_one/homelink/vault.py` | — | Production-ready |
| **H.O.M.E. L.I.N.K. (Registry)** | `guardian_one/homelink/registry.py` | — | Production-ready |
| **H.O.M.E. L.I.N.K. (Monitor)** | `guardian_one/homelink/monitor.py` | — | Production-ready |
| **CLI entry point** | `main.py` | 1067 | 38 commands, all working |

### What Needs Work

| Component | File | Status | Issue |
|-----------|------|--------|-------|
| **Mediator** | `guardian_one/core/mediator.py` | 154 lines, **unused** | Infrastructure exists (conflict detection, priority rules) but no agents submit proposals during normal runs |
| **Sandbox/Evaluator** | `guardian_one/core/sandbox.py` / `evaluator.py` | Partial | Deploys Chronos + Archivist only; evaluation metrics/thresholds unclear |
| **Dev Panel** | `guardian_one/web/app.py` | Exists | Web-based dev panel — not deeply integrated |

---

## Agent Registry

Guardian bootstraps 6 agents in `_build_agents()`:

| Agent | Class | Allowed Resources | Status |
|-------|-------|--------------------|--------|
| Chronos | `Chronos` | Google Calendar, schedule data | Fully implemented |
| Archivist | `Archivist` | File system, privacy tools | Fully implemented (APIs stubbed) |
| CFO | `CFO` | Plaid, Empower, Rocket Money, Excel | Fully implemented |
| DoorDash | `DoorDashAgent` | DoorDash API | Fully implemented |
| Gmail | `GmailAgent` | Gmail API (OAuth2) | Fully implemented |
| WebArchitect | `WebArchitect` | n8n, website domains | Fully implemented |

**Not auto-registered** (loaded on-demand via CLI flags):
- `DeviceAgent` — IoT/smart home management
- `WebsiteManager` — Per-site build/deploy pipelines

---

## Architecture: How Guardian Works

```
1. main.py parses CLI args
2. GuardianOne.__init__():
   - Loads config from guardian_config.yaml
   - Boots H.O.M.E. L.I.N.K. (Gateway, Vault, Registry, Monitor)
   - Seeds Vault from .env (NOTION_TOKEN, OLLAMA_API_KEY, etc.)
   - Creates AIEngine (Ollama primary, Anthropic fallback)
   - Calls _build_agents() → registers 6 agents
   - For each agent: creates AccessPolicy, calls initialize(), injects AI engine
3. run_all() → calls each agent's run() → collects reports
4. daily_summary() → aggregates all agent reports
5. Guardian exposes get_agent(name) for cross-agent access
```

### Agent Lifecycle

```python
class BaseAgent(ABC):
    def initialize(self) -> None: ...   # Setup (called once)
    def run(self) -> None: ...          # Execute duties (called each cycle)
    def report(self) -> AgentReport: ...  # Return structured status
    def shutdown(self) -> None: ...     # Cleanup (optional)

    # AI integration (provided by Guardian after registration):
    def think(self, prompt, system=None, context=None) -> str  # Stateful reasoning
    def think_quick(self, prompt) -> str                       # Stateless one-shot
```

### AI Engine

```python
ai_engine = AIEngine(config)
ai_engine.reason(agent_name, prompt, system, context)   # Stateful, per-agent memory
ai_engine.reason_stateless(prompt, system, context)      # One-shot, no memory
ai_engine.is_available()                                  # Any backend online?
ai_engine.status()                                        # Full status dict
```

- **Ollama**: Primary, local, sovereign — model configurable in YAML
- **Anthropic Claude**: Fallback when Ollama offline
- **Memory**: Sliding window per agent (max 50 messages default)
- **Audit**: All AI interactions logged (provider, model, tokens, latency)

---

## CLI Commands (38 total in main.py)

### Core
```bash
python main.py                    # Run all agents once + daily summary
python main.py --summary          # Daily summary only
python main.py --schedule         # Interactive scheduler (pause/resume/interval)
python main.py --agent NAME       # Run single agent
python main.py --sandbox          # Sandbox deployment
python main.py --eval-interval N  # Evaluation cycle interval
```

### Financial (CFO)
```bash
python main.py --dashboard        # CFO Excel dashboard
python main.py --validate         # CFO validation report
python main.py --sync             # Continuous financial sync
python main.py --sync-once        # Single financial sync
python main.py --connect          # Plaid OAuth link server
python main.py --csv PATH         # Parse Rocket Money CSV
```

### Calendar (Chronos)
```bash
python main.py --calendar         # Today's schedule
python main.py --calendar-week    # This week's schedule
python main.py --calendar-sync    # Sync Google Calendar + bills
python main.py --calendar-auth    # Google Calendar OAuth
```

### Websites
```bash
python main.py --websites         # All site status
python main.py --website-build X  # Build site(s)
python main.py --website-deploy X # Deploy site(s)
python main.py --website-sync     # Push dashboards to Notion
python main.py --security-review  # Security remediation tracking
python main.py --security-sync    # Push security dashboard to Notion
```

### Communication
```bash
python main.py --gmail            # Gmail inbox + CSV check
python main.py --notify           # Daily review notifications
python main.py --notify-test      # Test notification
python main.py --notion-sync      # Full Notion workspace sync
python main.py --notion-preview   # Preview Notion pages
```

### Infrastructure
```bash
python main.py --homelink         # H.O.M.E. L.I.N.K. status
python main.py --brief            # Weekly security brief
python main.py --ollama           # Ollama model status
python main.py --ollama-benchmark # Benchmark Ollama
python main.py --ollama-pull      # Pull Ollama model
python main.py --connector-audit  # MCP attack surface audit
python main.py --devpanel         # Web dev panel
```

### IoT / Smart Home
```bash
python main.py --devices          # Device inventory
python main.py --device-audit     # Security audit
python main.py --scene NAME       # Activate scene
python main.py --home-event TYPE  # Trigger automation
python main.py --flipper          # Flipper Zero status
python main.py --rooms            # Room layout
```

---

## Open Development Tracks

### Track 1: Mediator Integration (Priority)
The mediator (`guardian_one/core/mediator.py`) has full infrastructure:
- `Proposal` dataclass with agent, action, resources, priority, time_range
- `ConflictType` enum: TIME_OVERLAP, RESOURCE_CONTENTION, BUDGET_EXCEEDED
- Priority rules: Chronos > CFO > Archivist
- Thread-safe proposal queue with locking

**What's missing**: No agent submits proposals during `run()`. The mediator needs to be
wired into the agent lifecycle so agents submit proposed actions before executing them,
and the mediator resolves conflicts in real-time.

### Track 2: CFO Conversational Router (Spec Ready)
See `HANDOFF_CFO_ROUTER.md` — complete spec for `--ask` and `--chat` commands.

### Track 3: Sandbox & Evaluator
- Currently only deploys Chronos + Archivist
- Evaluation metrics/thresholds undefined
- Could be expanded to test all agents in isolation

### Track 4: Dev Panel Web UI
- `--devpanel` flag exists, `guardian_one/web/app.py` exists
- Needs review and deeper integration with agent status

### Track 5: Cross-Agent Coordination
- Gmail detects Rocket Money CSVs → CFO ingests them (partially wired)
- Chronos syncs bills to calendar from CFO (working)
- DoorDash checks Chronos for meal timing (implemented)
- More cross-agent workflows could be added

---

## Running Tests

```bash
pytest tests/ -v                    # All 200+ tests
pytest tests/test_guardian.py -v    # Guardian coordinator tests
pytest tests/test_agents.py -v     # Agent lifecycle tests
pytest tests/test_ai_engine.py -v  # AI engine tests
pytest tests/test_mediator.py -v   # Mediator tests
pytest tests/test_scheduler.py -v  # Scheduler tests
pytest tests/test_audit.py -v      # Audit logging tests
pytest tests/test_homelink.py -v   # H.O.M.E. L.I.N.K. tests
```

---

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest/transit
2. **Write-only Notion** — Push operational data, never read for decisions
3. **Content gate** — PHI/PII blocked before any external sync
4. **Audit everything** — Immutable log of all agent actions
5. **On-demand credentials** — Tokens from Vault per-request, never cached
6. **Agent isolation** — Each agent has defined allowed_resources
7. **AI optional** — System works without AI (AI adds polish, not core logic)

---

## Config

- Primary: `config/guardian_config.yaml`
- Secrets: `.env` (NOTION_TOKEN, OLLAMA_API_KEY, PLAID_CLIENT_ID, etc.)
- Vault: AES-256-GCM encrypted credential storage
