# Guardian One — OneOS Evolution: Phase 1-5 Implementation Handoff

**Owner:** Jeremy Paulo Salvino Tabernero
**Created:** 2026-03-24
**Purpose:** Complete instructions for building the next-generation architecture on top of the existing Guardian One platform.

**Notion HQ:** Guardian One HQ page contains ADR-001, System Design, Production Roadmap, Agent Registry, Integration Health, and Deliverables databases. The System Design doc defines a 4-layer architecture (H.O.M.E. L.I.N.K. → Agents → Orchestration → Control Plane).

---

## Operational Reality (from Daily Handoff 2026-03-23)

Before starting any phase, understand what's **actually working vs. shell**:

### Working Now
- Daemon boots, runs 7 agents on intervals, logs everything
- Ollama-powered chat interface with live financial data context
- CFO has real ledger data from Rocket Money CSV import
- Device registry with full 56-device inventory
- Audit log captures every agent action (11,558+ entries)
- Health monitor checks infrastructure every 60 seconds
- Encrypted vault for credential storage (dev passphrase)

### Not Working Yet (needs live API connections)
- Google Calendar sync (OAuth not completed)
- Gmail inbox monitoring (OAuth not completed)
- Plaid/Empower live financial sync (tokens not exchanged)
- DoorDash API (not connected)
- n8n workflow automation (not configured)
- **Agents do NOT call `self.think()` during run cycles** — AI reasoning exists but is unused in scheduled runs

### Pre-Phase Priorities (from Notion roadmap)
These are quick wins that should be wired before or alongside Phase 1:
1. **Wire agents to call `self.think()`** — the AI engine exists but agents don't use it during scheduled runs
2. **Add state diff detection** — agents should compare current vs. previous run, only report changes
3. **Production Vault passphrase** — replace dev passphrase before any real credentials go in
4. **Move CFO to SQLite** — enables trend analysis, not just snapshot reporting

---

## Current State (What Already Exists)

Before building anything, understand what's already production-ready:

### Core Infrastructure
| Component | File | Status |
|-----------|------|--------|
| Central Coordinator | `guardian_one/core/guardian.py` | `GuardianOne` class — boots agents, enforces access, produces summaries |
| Base Agent ABC | `guardian_one/core/base_agent.py` | `BaseAgent` with `initialize()`, `run()`, `report()`, `shutdown()`, `think()`, `think_quick()` |
| Daemon Mode | `guardian_one/core/daemon.py` | `GuardianDaemon` — scheduled execution, Flask health API (`/health`, `/status`, `/metrics`), state persistence, auto-pause after 5 failures |
| AI Engine | `guardian_one/core/ai_engine.py` | Dual-backend: Ollama (local primary) + Anthropic Claude (cloud fallback), per-agent memory, tool-use agentic loop |
| Mediator | `guardian_one/core/mediator.py` | Priority-based conflict resolution (time overlap, resource contention), defers to owner on ties |
| Audit Log | `guardian_one/core/audit.py` | Append-only, severity-tagged, immutable records, pending review queue |
| Access Control | `guardian_one/core/security.py` | Role-based (OWNER > GUARDIAN > MENTOR > AGENT), per-agent resource scoping |
| Config | `guardian_one/core/config.py` | YAML-based config loader from `config/guardian_config.yaml` |
| Command Router | `guardian_one/core/command_router.py` | NLP intent detection for CFO queries, keyword-based with AI enhancement |
| Structured Logging | `guardian_one/core/logging.py` | JSON logging with daily rotation |
| Sandbox | `guardian_one/core/sandbox.py` | Deployment testing environment |
| Evaluator | `guardian_one/core/evaluator.py` | Performance metrics |

### 7 Subordinate Agents
| Agent | File | Purpose |
|-------|------|---------|
| Chronos | `agents/chronos.py` | Calendar, sleep, routines, scheduling |
| CFO | `agents/cfo.py` | Finances — accounts, bills, budgets, Plaid/Empower/Rocket Money |
| CFO Dashboard | `agents/cfo_dashboard.py` | Excel financial dashboard generation |
| Archivist | `agents/archivist.py` | Data sovereignty, file management, encryption |
| GmailAgent | `agents/gmail_agent.py` | Inbox monitoring, email categorization |
| WebArchitect | `agents/web_architect.py` | Website security, n8n deployment |
| WebsiteManager | `agents/website_manager.py` | Per-site build/deploy pipelines |
| DoorDashAgent | `agents/doordash.py` | Meal delivery coordination |
| DeviceAgent | `agents/device_agent.py` | IoT/smart home, automation, Flipper Zero |

### H.O.M.E. L.I.N.K. (API + Smart Home)
| Module | File | Purpose |
|--------|------|---------|
| Gateway | `homelink/gateway.py` | TLS 1.3, rate limiting, circuit breakers for all external API calls |
| Vault | `homelink/vault.py` | Fernet-encrypted credential storage, PBKDF2 key derivation, rotation tracking |
| Registry | `homelink/registry.py` | Integration catalog with threat models and rollback procedures |
| Monitor | `homelink/monitor.py` | API health monitoring, anomaly detection, weekly security briefs |
| Devices | `homelink/devices.py` | Device inventory, room model, Flipper Zero profiles |
| Automations | `homelink/automations.py` | Rule-based automation engine (routines, scenes, solar events) |

### Web Interface
| Component | File | Purpose |
|-----------|------|---------|
| Flask App | `web/app.py` | 15+ REST endpoints, dev panel, chat interface |
| Panel UI | `web/templates/panel.html` | System dashboard |
| Chat UI | `web/templates/chat.html` | Conversational interface with AI toggle |
| PWA | `web/static/manifest.json`, `web/static/sw.js` | Installable progressive web app |

### Integrations
| File | Purpose |
|------|---------|
| `integrations/notion_sync.py` | Write-only Notion workspace sync |
| `integrations/notion_website_sync.py` | Per-site Notion dashboards |
| `integrations/notion_remediation_sync.py` | Security remediation to Notion |
| `integrations/calendar_sync.py` | Google Calendar |
| `integrations/gmail_sync.py` | Gmail API |
| `integrations/financial_sync.py` | Plaid/Empower/Rocket Money |
| `integrations/doordash_sync.py` | DoorDash API |
| `integrations/n8n_sync.py` | n8n workflow automation |
| `integrations/ollama_sync.py` | Ollama model management |
| `integrations/zapier_sync.py` | Zapier automation bridge |
| `integrations/plaid_connect.py` | Plaid bank connection |
| `integrations/privacy_tools.py` | VPN/privacy services |

### Test Suite
- **878 pytest test cases** across 25+ test files in `tests/`
- All tests use fake providers (no real API calls)
- CI: `.github/workflows/test.yml` runs pytest on push/PR

### CLI Entry Point
- `main.py` — 25+ CLI commands via argparse
- See docstring at top of `main.py` for full command list

---

## Architecture Patterns You Must Follow

1. **Every agent extends `BaseAgent`** — implement `initialize()`, `run()`, `report()`
2. **AI via `self.think(prompt, context)`** — returns `AIResponse`; falls back gracefully if AI offline
3. **All external API calls route through Gateway** — TLS enforcement, rate limiting, circuit breakers
4. **Credentials from Vault only** — loaded per-request, never cached in memory
5. **Write-only Notion** — push operational data, never read for decisions
6. **Content gate** — PHI/PII regex scanner blocks sensitive data before any external sync
7. **Audit everything** — every agent action logged immutably via `self.log(action, severity, details)`
8. **Config from YAML** — `config/guardian_config.yaml`, loaded via `load_config()`
9. **Tests use fake providers** — no real API calls in tests

---

## Phase 1: Event Bus (Foundation Layer)

**Goal:** Replace direct `run_agent()` calls with a publish/subscribe event system so agents can react to each other's outputs without tight coupling. Per the Notion System Design: "Add an Event Bus (in-process pub/sub, upgradeable to Redis Streams) so agents can emit typed events and other agents can subscribe to relevant topics."

### What to Build

**New file: `guardian_one/core/event_bus.py`**

```
EventBus class:
- publish(event_type: str, payload: dict, source: str) -> None
- subscribe(event_type: str, handler: Callable) -> str  # returns subscription_id
- unsubscribe(subscription_id: str) -> None
- event_history(limit: int) -> list[Event]

Event dataclass:
- event_id: str (uuid)
- event_type: str (e.g., "cfo.budget_alert", "chronos.schedule_conflict")
- payload: dict
- source: str (agent name)
- timestamp: str (ISO UTC)

EventType constants (enum or string constants):
- AGENT_RUN_COMPLETE = "agent.run_complete"
- AGENT_ERROR = "agent.error"
- CFO_BUDGET_ALERT = "cfo.budget_alert"
- CFO_BILL_DUE = "cfo.bill_due"
- CFO_ANOMALY = "cfo.anomaly"
- CHRONOS_SCHEDULE_CONFLICT = "chronos.schedule_conflict"
- CHRONOS_REMINDER = "chronos.reminder"
- GMAIL_URGENT = "gmail.urgent_email"
- ARCHIVIST_BACKUP_NEEDED = "archivist.backup_needed"
- DEVICE_ALERT = "device.alert"
- DEVICE_SCENE_ACTIVATED = "device.scene_activated"
- HOMELINK_CIRCUIT_OPEN = "homelink.circuit_open"
- HOMELINK_ANOMALY = "homelink.anomaly"
- SYSTEM_BOOT = "system.boot"
- SYSTEM_SHUTDOWN = "system.shutdown"
```

### Integration Points

1. **Inject EventBus into `GuardianOne.__init__()`** — create `self.event_bus = EventBus(audit=self.audit)`
2. **Pass to each agent** — add `set_event_bus(bus)` to `BaseAgent`, called in `register_agent()`
3. **Add `self.emit(event_type, payload)` convenience method to `BaseAgent`** — wraps `self._event_bus.publish()`
4. **Wire into `run_agent()`** — after each agent run, auto-publish `AGENT_RUN_COMPLETE` with report data
5. **Wire into daemon** — daemon subscribes to `AGENT_ERROR` for auto-pause logic
6. **Gateway circuit events** — Gateway emits events on circuit state changes (per System Design Section 3.1)
7. **Monitor anomaly events** — Monitor emits anomaly events via bus instead of just logging (per System Design Section 3.4)

### OneOS System Design Additions (from Notion)
The System Design doc specifies these Event Bus-adjacent upgrades to existing components:
- **Gateway**: Event emission on circuit state changes, request priority queuing, per-agent request budgets
- **Monitor**: Continuous daemon-driven monitoring, anomaly-triggered agent alerts via Event Bus, historical trend storage
- **Registry**: Plugin-contributed integrations, dependency graph, automatic health degradation notices

### Constraints
- Thread-safe (use `threading.Lock`)
- All events audit-logged
- Event history capped (configurable, default 1000)
- Handlers execute synchronously in subscriber order (async can come in Phase 2)
- No breaking changes to existing `run_agent()` / `run_all()` flow

### Tests to Write
- `tests/test_event_bus.py` — publish/subscribe, unsubscribe, event history, thread safety, audit logging
- Update `tests/test_guardian.py` — verify event bus is created and injected
- Update `tests/test_daemon.py` — verify daemon subscribes to error events

---

## Phase 2: FastAPI Migration + Async Events

**Goal:** Replace Flask with FastAPI for better async support, WebSocket streaming, and auto-generated API docs. Make event bus async-capable.

### What to Change

**Replace `guardian_one/web/app.py`** (currently Flask):
- Migrate all 15+ endpoints to FastAPI
- Keep same URL structure (`/api/status`, `/api/agents`, etc.)
- Add WebSocket endpoint `/ws/events` for real-time event streaming to the PWA
- Add OpenAPI docs at `/docs` (FastAPI built-in)
- Keep templates working (use `Jinja2Templates` from Starlette)

**Replace `guardian_one/core/daemon.py`** health server:
- Replace Flask health endpoints with FastAPI (or keep separate — evaluate)
- Consider merging daemon health + web panel into single FastAPI app

**Upgrade `guardian_one/core/event_bus.py`**:
- Add `async_publish()` and `async_subscribe()` for async handlers
- WebSocket bridge: events auto-stream to connected clients
- Keep sync API intact for backward compat

### New Dependencies
- `fastapi`
- `uvicorn`
- `websockets`
- Remove `flask` dependency

### Migration Checklist
1. Port each Flask route to FastAPI (same response format)
2. Update `main.py --devpanel` to use `uvicorn.run()`
3. Update `web/templates/panel.html` and `chat.html` — add WebSocket event listener
4. Update all tests that reference Flask test client -> FastAPI `TestClient`
5. Update `requirements.txt` / `pyproject.toml`

### Tests
- `tests/test_devpanel.py` — migrate to FastAPI TestClient
- `tests/test_websocket.py` — new: test event streaming
- All existing API tests must pass with new backend

---

## Phase 3: Plugin System (Dynamic Agent Loading)

**Goal:** Allow new agents to be added as plugins without modifying core code. Drop a Python file in `plugins/`, it auto-registers.

### What to Build

**New directory: `guardian_one/plugins/`**

**New file: `guardian_one/core/plugin_loader.py`**

```
PluginLoader class:
- discover(plugin_dir: Path) -> list[PluginMeta]
- load(plugin_meta: PluginMeta) -> BaseAgent
- load_all(plugin_dir: Path) -> list[BaseAgent]
- validate(plugin_meta: PluginMeta) -> list[str]  # returns validation errors

PluginMeta dataclass:
- name: str
- version: str
- author: str
- description: str
- agent_class: str  # fully qualified class name
- config_schema: dict  # JSON schema for plugin-specific config
- required_resources: list[str]
- dependencies: list[str]  # other plugins this depends on
```

### Plugin Contract
Each plugin is a Python file in `guardian_one/plugins/` that:
1. Contains a class extending `BaseAgent`
2. Has a module-level `PLUGIN_META` dict with name, version, author, description
3. Optionally has a `CONFIG_SCHEMA` dict for validation
4. Is auto-discovered at boot by `PluginLoader`

### Example Plugin Structure
```python
# guardian_one/plugins/example_agent.py

PLUGIN_META = {
    "name": "example_agent",
    "version": "1.0.0",
    "author": "Jeremy",
    "description": "Example plugin agent",
    "required_resources": ["example_api"],
}

class ExampleAgent(BaseAgent):
    def initialize(self): ...
    def run(self): ...
    def report(self): ...
```

### Integration Points
1. **`GuardianOne.__init__()` or `_build_agents()`** — call `PluginLoader.load_all()` after hardcoded agents
2. **Add `plugins:` section to `guardian_config.yaml`** — per-plugin enable/disable and config
3. **Plugin isolation** — each plugin gets its own `AgentConfig` with scoped `allowed_resources`
4. **Plugin lifecycle** — initialize, run, report, shutdown — same as core agents

### Security
- Plugins run in same process but with resource scoping via `AccessController`
- Plugin validation: must extend `BaseAgent`, must have `PLUGIN_META`
- No arbitrary code execution outside the `BaseAgent` contract

### Tests
- `tests/test_plugin_loader.py` — discovery, loading, validation, error handling
- Test with a sample plugin in `tests/fixtures/plugins/`

---

## Phase 4: Cloud Relay (Multi-Machine Coordination)

**Goal:** Enable Guardian One to run across multiple machines (current laptop + ROG X 64GB) with coordinated agent execution, shared state, and leader election.

### Notion System Design Constraints (Section 3.5)
The System Design doc is very specific about the Cloud Relay:
- **No PII, no credentials, no decision data.** The relay handles ONLY: agent heartbeats, wake signals, and encrypted state sync blobs.
- **Stateless.** No persistent storage on the relay. It is a message pass-through.
- **Authenticated.** Device-to-relay communication uses mTLS with device certificates stored in Vault.
- **Minimal.** Target implementation: <500 lines of Python (FastAPI or aiohttp).
- **Hosted on existing Cloud VPS** (same infra as jtmdai.com).

### What to Build

**New file: `guardian_one/homelink/relay.py`**

```
CloudRelay class:
- connect(peer_url: str) -> bool
- disconnect(peer_id: str) -> None
- send(peer_id: str, message: RelayMessage) -> bool
- broadcast(message: RelayMessage) -> dict[str, bool]
- peers() -> list[PeerInfo]
- elect_leader() -> str  # returns leader peer_id

RelayMessage dataclass:
- message_id: str
- message_type: str  # "event", "state_sync", "heartbeat", "leader_election"
- payload: dict
- source_peer: str
- timestamp: str

PeerInfo dataclass:
- peer_id: str
- hostname: str
- ip: str
- port: int
- last_heartbeat: str
- is_leader: bool
- agent_count: int
```

### Architecture
- **Transport:** HTTPS + WebSocket between peers (reuse FastAPI from Phase 2)
- **Discovery:** Manual peer configuration in `guardian_config.yaml` under `relay:` section
- **Leader Election:** Simple bully algorithm — highest-priority peer is leader
- **State Sync:** Leader broadcasts state changes; followers apply
- **Event Bridge:** Events published on one machine propagate to peers via relay

### Leader Responsibilities
- Runs scheduling (daemon loop)
- Assigns agents to peers based on capability/load
- Holds authoritative state
- Followers run assigned agents and report back

### Config Addition
```yaml
relay:
  enabled: false
  peer_id: "macbook-pro"
  peers:
    - id: "rog-x-64gb"
      url: "https://192.168.1.x:5200"
      priority: 2
  heartbeat_interval_seconds: 30
  leader_priority: 1  # lower = higher priority
```

### Security
- All relay traffic TLS-encrypted
- Peer authentication via mTLS with device certificates (stored in Vault)
- Relay messages audit-logged
- Vault additions for Phase 4: daemon-mode auto-unlock (OS keychain), credential lease model (time-limited decrypt tokens), multi-device Vault sync (encrypted blob replication, never decrypted in transit)

### Tests
- `tests/test_relay.py` — peer connection, heartbeat, leader election, state sync
- Test with mock peers (no real network)

---

## Phase 5: AI-Powered Mediator (Intelligent Conflict Resolution)

**Goal:** Replace the current rule-based mediator with an AI-powered one that can reason about complex multi-agent conflicts, learn from past resolutions, and explain decisions.

### What to Change

**Upgrade `guardian_one/core/mediator.py`**:

```
Current: Priority-based rules (chronos > cfo > archivist)
New: AI reasoning with context from:
  - Conflict history
  - Agent reports
  - User preferences (learned over time)
  - Time sensitivity
  - Financial impact
  - Schedule constraints
```

### New Mediator Capabilities

1. **AI-Powered Resolution**
   - Use `self.think()` (via AI Engine) to analyze conflicts
   - Provide structured context: both proposals, conflict history, agent states
   - AI returns resolution + rationale in natural language

2. **Resolution Learning**
   - Track which resolutions Jeremy approves/overrides
   - Build a preference model: "Jeremy always prioritizes X over Y in context Z"
   - Store in `data/mediator_preferences.json`

3. **Multi-Agent Conflict Chains**
   - Handle cascading conflicts (A conflicts with B, resolution affects C)
   - Dependency graph for proposals

4. **Explanation System**
   - Every resolution includes human-readable rationale
   - Chat interface can query: "Why did you resolve X that way?"

### Implementation

```python
class AIMediatorV2(Mediator):
    """AI-enhanced mediator that reasons about conflicts."""

    def _resolve_with_ai(self, proposals: list[Proposal]) -> ConflictRecord:
        context = {
            "proposals": [asdict(p) for p in proposals],
            "history": self._recent_resolutions(limit=10),
            "preferences": self._load_preferences(),
        }
        response = self.think(
            "Analyze these conflicting proposals and recommend a resolution. "
            "Consider priority, time sensitivity, cost, and Jeremy's past preferences.",
            context=context,
        )
        # Parse AI response into resolution
        ...

    def _load_preferences(self) -> dict:
        # Load from data/mediator_preferences.json
        ...

    def record_feedback(self, conflict_id: str, approved: bool, override: Resolution | None = None):
        # Jeremy approves or overrides — update preference model
        ...
```

### Fallback
- If AI is offline, fall back to current rule-based resolution (Phase 5 is backward-compatible)
- All AI resolutions are flagged `requires_review=True` until confidence is established

### Tests
- `tests/test_mediator.py` — update existing + add AI resolution tests
- Test preference learning
- Test fallback to rule-based when AI offline

---

## Implementation Order & Dependencies

```
Phase 1: Event Bus
  +-- No dependencies, pure addition
  +-- Foundation for everything else

Phase 2: FastAPI Migration + Async Events
  +-- Depends on: Phase 1 (event bus for WebSocket streaming)
  +-- Enables: real-time UI, async agent execution

Phase 3: Plugin System
  +-- Depends on: Phase 1 (plugins emit/subscribe to events)
  +-- Independent of Phase 2 (works with sync or async)

Phase 4: Cloud Relay
  +-- Depends on: Phase 1 (relay bridges event buses across machines)
  +-- Depends on: Phase 2 (uses FastAPI/WebSocket for transport)

Phase 5: AI Mediator
  +-- Depends on: Phase 1 (subscribes to conflict events)
  +-- Independent of Phases 2-4 (works standalone)
```

---

## Critical Rules for Every Phase

1. **Never break existing tests.** Run `pytest tests/ -v` after every change. Currently 878 tests.
2. **Never break existing CLI commands.** `main.py` must keep working.
3. **Every new module gets tests.** Minimum 20 test cases per new file.
4. **Update `CLAUDE.md`** when adding new files/directories to the architecture.
5. **Update `config/guardian_config.yaml`** when adding new configurable features.
6. **All new code follows existing patterns** — look at how existing agents/modules work.
7. **No real API calls in tests** — use mocks/fakes like existing tests do.
8. **Audit everything** — new subsystems must log to the audit trail.
9. **Thread safety** — Guardian One is multi-threaded (daemon + health server + agents).
10. **Branch:** Develop on the designated feature branch, not main.

---

## Running the Project

```bash
# Setup
cd ~/JT
pip install -r requirements.txt

# Run tests (do this first to verify everything works)
pytest tests/ -v

# Run all agents once
python main.py

# Start web panel
python main.py --devpanel

# Start daemon
python main.py --daemon

# Chat interface
python main.py --devpanel  # then visit http://localhost:5100/chat
```

---

## File Tree Reference

```
guardian_one/
  agents/
    chronos.py, archivist.py, cfo.py, cfo_dashboard.py
    doordash.py, gmail_agent.py, web_architect.py
    website_manager.py, device_agent.py
  core/
    guardian.py          # Central coordinator (start here)
    base_agent.py        # Agent ABC (every agent extends this)
    ai_engine.py         # Ollama + Anthropic dual backend
    daemon.py            # Headless scheduler + health API
    mediator.py          # Conflict resolution (Phase 5 target)
    command_router.py    # NLP intent detection for CFO
    chat_ui.py           # Chat UI logic
    audit.py, security.py, config.py, logging.py
    evaluator.py, sandbox.py, scheduler.py
    security_remediation.py, web_tools.py
  homelink/
    gateway.py, vault.py, registry.py, monitor.py
    devices.py, automations.py
  integrations/
    notion_sync.py, notion_website_sync.py, notion_remediation_sync.py
    calendar_sync.py, gmail_sync.py, financial_sync.py
    doordash_sync.py, n8n_sync.py, ollama_sync.py
    zapier_sync.py, plaid_connect.py, privacy_tools.py
  templates/
    agent_template.py
  web/
    app.py               # Flask REST API + chat (Phase 2: migrate to FastAPI)
    templates/panel.html, chat.html
    static/manifest.json, sw.js
  utils/
    encryption.py, notifications.py
config/guardian_config.yaml   # System configuration
main.py                       # CLI entry point (25+ commands)
tests/                        # 878 pytest tests
```

---

## Quick Start for New Session

1. Read `CLAUDE.md` for project context
2. Read this `HANDOFF.md` for the evolution plan
3. Run `pytest tests/ -v` to verify baseline
4. Start with **Phase 1: Event Bus** — it's the foundation for everything
5. Branch: `claude/build-guardian-one-ym6nF` (or create a new feature branch)

Good luck. Build it right. Jeremy's counting on you.
