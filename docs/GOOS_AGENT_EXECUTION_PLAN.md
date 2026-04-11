# GOOS V1.0 — AI Agent Execution Plan

## Mental Model: The Sovereign Machine

```
┌─────────────────────────────────────────────────────────────┐
│                    GUARDIAN ONE OS (GOOS)                     │
│              "The Sovereign Machine for Humans"               │
│                                                               │
│  One system. Three brains. Your data. Your rules.            │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │  GUARDIAN    │  │    CFO       │  │      VARYS          │ │
│  │  The Mind    │  │  The Ledger  │  │   The Watcher       │ │
│  │  (Cloud)     │  │  (Finance)   │  │   (Local/Physical)  │ │
│  │             │  │             │  │                     │ │
│  │  Thinks.    │  │  Counts.    │  │  Protects.          │ │
│  │  Plans.     │  │  Tracks.    │  │  Scans.             │ │
│  │  Coordinates│  │  Alerts.    │  │  Controls devices.  │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                     │             │
│         └────────────────┼─────────────────────┘             │
│                          │                                    │
│                   ┌──────┴──────┐                             │
│                   │  OVERLORD   │                             │
│                   │  (Infra)    │                             │
│                   │             │                             │
│                   │  Hosts.     │                             │
│                   │  Routes.    │                             │
│                   │  Bills.     │                             │
│                   │  Builds.    │                             │
│                   └─────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

**One sentence**: GOOS is a personal AI operating system where Guardian thinks
online, Varys protects locally, CFO manages money, and Overlord runs the
infrastructure that makes it all possible.

---

## Part 1: Honest Capability Assessment

### What Works TODAY (Production-Ready)

| Component | Status | Evidence |
|-----------|--------|----------|
| Guardian coordinator | WORKS | 531 lines, boots all agents, daily summaries |
| BaseAgent lifecycle | WORKS | 391 lines, 28 tests, initialize→run→report→shutdown |
| AI Engine (Ollama + Claude) | WORKS | 483 lines, 45 tests, local-first with cloud fallback |
| Vault (encrypted credentials) | WORKS | 229 lines, 18 tests, AES-256, PBKDF2 480K iterations |
| Gateway (TLS, rate limit) | WORKS | 385 lines, circuit breaker, request auditing |
| Audit logging | WORKS | Immutable JSONL, severity tags, PII redaction |
| Access control (RBAC) | WORKS | 4 access levels, per-agent resource scoping |
| CFO agent | WORKS | 1,717 lines, 35 tests, Plaid/Empower/Rocket Money |
| Chronos agent | WORKS | 423 lines, calendar sync, conflict detection |
| DoorDash agent | WORKS | 597 lines, 39 tests, JWT auth, delivery tracking |
| Gmail agent | WORKS | 377 lines, 65 tests, inbox monitoring |
| Device agent (IoT) | WORKS | 795 lines, 153 tests, Hue/Kasa/Govee control |
| WebArchitect agent | WORKS | 467 lines, 73 tests, n8n workflows |
| Varys (security) | WORKS | 337 lines, Sigma rules, anomaly detection, LLM triage |
| MCP server | WORKS | 358 lines, stdio + SSE transport |
| GOOS registration | WORKS | 246 lines, 44 tests, email verify, PBKDF2 auth |
| GOOS onboarding | WORKS | 340 lines, 44 tests, 10-step guided flow |
| Config system | WORKS | YAML-driven, env-var overrides |
| Test suite | WORKS | 1,682/1,685 passing (99.8%) |

### What's PARTIALLY Done

| Component | % Done | Gap |
|-----------|--------|-----|
| Homelink IoT drivers | 60% | Hue/Kasa/Govee work; Zigbee, Matter, cameras stubbed |
| Network scanner | 50% | nmap skeleton; no continuous monitoring |
| Varys detection rules | 40% | Framework complete; needs more Sigma rules |
| Varys containment | 40% | Isolate-host skeleton; no real iptables/firewall |
| Privacy tools | 40% | VPN status detection only |
| CFO dashboard (Excel) | 30% | Template skeleton, no data binding |
| Ring doorbell | 30% | Event polling defined, no streaming |
| DB schema | 20% | SQL/Neo4j/Dgraph DEFINED but zero connection code |

### What DOES NOT EXIST Yet

| Component | Status | Required For |
|-----------|--------|--------------|
| SQLite persistence | Not started | Data survival across restarts |
| Systemd daemon | Not started | Always-on operation |
| Health check API | Not started | Monitoring, uptime |
| Stripe/billing | Not started | Paid tiers |
| VR/3D world | Not started | Immersive GOOS interface |
| Mobile app | Not started | Phone access |
| Kubernetes | Not started | Cloud scaling |
| Polyglot layer (C/Go/Rust) | Not started | Hardware-level interfaces |
| Overlord infrastructure | Not started | Website hosting, transactions |
| Quantum-paired agents | Not started | Local↔cloud entanglement |

---

## Part 2: The Overlord System

The Overlord is the **infrastructure brain** — it doesn't think about your
calendar or your money. It thinks about servers, websites, builds, billing,
and keeping the platform alive.

### Overlord Responsibilities

```
OVERLORD (Infrastructure Layer)
├── Website Management
│   ├── Build pipelines (Cloudflare Pages/Workers)
│   ├── SSL certificate monitoring
│   ├── CDN configuration
│   └── Domain DNS management
│
├── Transaction Engine
│   ├── Stripe integration (membership billing)
│   ├── Tier upgrades/downgrades
│   ├── Invoice generation
│   └── Usage metering
│
├── Platform Operations
│   ├── Health checks (/health, /status, /metrics)
│   ├── Service orchestration (Docker/systemd)
│   ├── Log aggregation and alerting
│   └── Backup scheduling (CitadelOne)
│
├── Client-Facing Services
│   ├── GOOS website (registration portal)
│   ├── API gateway (per-client rate limiting)
│   ├── WebSocket connections (real-time updates)
│   └── File upload/storage (encrypted per-client)
│
└── Agent Infrastructure
    ├── Agent deployment (spin up per-client agents)
    ├── Resource allocation (CPU/memory per tier)
    ├── Inter-agent message bus
    └── Telemetry and performance monitoring
```

### What Exists vs What's Needed

| Overlord Function | Current State | File |
|-------------------|---------------|------|
| Website build/deploy | Partial — WebArchitect does Cloudflare | `agents/web_architect.py` |
| Health endpoints | NOT STARTED | — |
| Stripe billing | NOT STARTED | — |
| Docker orchestration | Template exists | `homelink/iot_stack.py` |
| API gateway | WORKS (single-user) | `homelink/gateway.py` |
| Backup/restore | WORKS | `core/citadel.py` |
| Service monitoring | WORKS | `homelink/monitor.py` |

---

## Part 3: Quantum-Paired Agents (Local ↔ Cloud Entanglement)

### Concept

When a user registers, GOOS creates TWO agents simultaneously:

```
CLOUD AGENT (Guardian-side)          LOCAL AGENT (Varys-side)
┌────────────────────────┐           ┌────────────────────────┐
│  Agent-Cloud-{uuid}    │◄─────────►│  Agent-Local-{uuid}    │
│                        │  Encrypted│                        │
│  • Cloud APIs          │  Tunnel   │  • File system access  │
│  • Internet services   │  (Always  │  • IoT device control  │
│  • Heavy AI reasoning  │   Synced) │  • LAN scanning        │
│  • Financial APIs      │           │  • Ollama (local AI)   │
│  • Email/calendar      │           │  • Offline operation   │
└────────────────────────┘           └────────────────────────┘
         │                                     │
    Shares state:                         Shares state:
    • User preferences                   • Device inventory
    • Agent decisions                    • Security alerts
    • Financial data                     • Network topology
    • Conversation history               • Local file index
```

### The "Entanglement" Contract

1. **Shared identity** — Same `client_id`, same encryption keys
2. **Bidirectional sync** — Changes on either side propagate
3. **Offline resilience** — Local agent queues; syncs when reconnected
4. **Split processing** — Cloud handles APIs; local handles hardware
5. **Single view** — User sees ONE agent, not two

### Implementation Path

| Step | What | Uses |
|------|------|------|
| 1 | Registration creates both agent records | `goos/client.py` (exists) |
| 2 | Varys installer registers local node | `goos/sentinel.py` (exists) |
| 3 | Encrypted tunnel established | Tailscale/WireGuard (partial) |
| 4 | State sync protocol | NEW — JSON delta sync over tunnel |
| 5 | Split-brain resolution | NEW — cloud wins for API data, local wins for devices |
| 6 | Unified API | NEW — queries route to correct side transparently |

---

## Part 4: Database Architecture

### Current State: JSON files (fragile)
### Target State: SQLite local + PostgreSQL cloud

```
LOCAL (Varys)                        CLOUD (Guardian)
┌─────────────────────┐              ┌──────────────────────┐
│  SQLite              │              │  PostgreSQL           │
│  • Device inventory  │  ──sync──►  │  • Client accounts    │
│  • Security alerts   │              │  • Financial data     │
│  • Network scans     │  ◄──sync──  │  • Agent state        │
│  • Offline queue     │              │  • Audit trail        │
│  • Local preferences │              │  • Billing/tiers      │
└─────────────────────┘              └──────────────────────┘
```

### Step-by-Step Database Plan

1. Initialize SQLite from existing schema (`core/db_schema.py` — 452 lines defined)
2. Migrate CFO ledger from JSON → SQLite
3. Migrate audit log from JSONL → SQLite
4. Add connection pooling and WAL mode
5. Build sync protocol (local SQLite ↔ cloud PostgreSQL)
6. Encrypt database at rest (SQLCipher or application-level)

---

## Part 5: VR World Layer (GOOS Immersive)

### Concept

The VR layer is a **3D representation of the GOOS environment** where:
- Each agent has a workspace (room/zone)
- Users have an avatar
- The environment reflects real-world data (weather, location, time)
- Agents can be "visited" to interact directly

### Architecture

```
VR WORLD (GOOS Immersive)
├── Engine: Three.js / Babylon.js (WebGL, runs in browser)
├── World Structure:
│   ├── Hub (central command — Guardian's domain)
│   ├── Vault (CFO's financial visualization room)
│   ├── Watchtower (Varys's security operations center)
│   ├── Workshop (DevCoach's code lab)
│   ├── Library (Archivist's data archive)
│   ├── Kitchen (DoorDash meal planning)
│   ├── Calendar Room (Chronos time management)
│   └── User's Personal Space (customizable)
│
├── User Avatar:
│   ├── Customizable appearance
│   ├── Geolocation-aware (real weather in VR sky)
│   ├── Time-of-day lighting
│   └── Notification badges on agents
│
├── Agent Interfaces:
│   ├── Each agent has a templated UI panel in their room
│   ├── Agents can "borrow" skills from each other
│   ├── Visual data dashboards (3D charts, network maps)
│   └── Chat interface overlays
│
└── Technology Stack:
    ├── Three.js (3D rendering)
    ├── React Three Fiber (React integration)
    ├── WebSocket (real-time agent state)
    ├── WebXR (optional VR headset support)
    └── Progressive enhancement (works on phone/desktop/VR)
```

### Current State: DOES NOT EXIST
### Dependencies Needed: `three`, `@react-three/fiber`, `@react-three/drei`

---

## Part 6: Polyglot Systems Layer

### Why Low-Level Languages?

| Language | Purpose in GOOS |
|----------|----------------|
| **C** | Kernel modules for network monitoring, eBPF programs |
| **Go** | Varys sentinel daemon, tunnel management, high-perf networking |
| **Rust** | Encryption primitives, file system watchers, IoT protocol parsers |
| **Assembly** | Hardware fingerprinting, CPU feature detection |
| **Carbon** | Future C++ interop for performance-critical paths |
| **V** | Lightweight IoT device drivers |

### Implementation Priority

```
Phase 1 (Now):     Python (everything) ← WE ARE HERE
Phase 2 (6 months): Go (Varys daemon, tunnel, network scanner)
Phase 3 (12 months): Rust (crypto, file watchers, protocol parsers)
Phase 4 (18 months): C (kernel modules, eBPF, hardware interfaces)
Phase 5 (24 months): WASM (browser-side compute for VR layer)
```

---

## Part 7: Step-by-Step Agent Execution Plan

### For Any AI Agent Working on GOOS

**Read this first. Understand the system. Then execute your assigned layer.**

---

### LAYER 0: Foundation (Must exist before anything else)

| Step | Task | Files | Status |
|------|------|-------|--------|
| 0.1 | SQLite initialization — connect `db_schema.py` to actual database | `core/db_schema.py` | NOT STARTED |
| 0.2 | Migrate CFO ledger from JSON to SQLite | `data/cfo_ledger.json` → SQLite | NOT STARTED |
| 0.3 | Migrate audit log from JSONL to SQLite | `logs/audit.jsonl` → SQLite | NOT STARTED |
| 0.4 | Systemd service file for Guardian daemon | NEW: `scripts/goos-guardian.service` | NOT STARTED |
| 0.5 | Health check endpoints (`/health`, `/status`) | `web/app.py` | NOT STARTED |
| 0.6 | Remove default vault passphrase | `core/security.py` | NOT STARTED |

**Agent instruction**: "You are building the foundation. Nothing else works without
persistent storage and a running daemon. Do steps 0.1-0.6 in order. Run
`pytest tests/` after each step. Do not proceed if tests fail."

---

### LAYER 1: Overlord Infrastructure

| Step | Task | Depends On |
|------|------|------------|
| 1.1 | Create `guardian_one/overlord/` package | Layer 0 complete |
| 1.2 | Build Stripe integration (subscription billing) | 1.1 |
| 1.3 | Build website deployment pipeline (Cloudflare API) | 1.1 |
| 1.4 | Build service orchestrator (Docker Compose generation) | 1.1 |
| 1.5 | Build metrics/telemetry collector | 1.1 + 0.5 |
| 1.6 | Wire Overlord into GOOS API | 1.1-1.5 |

**Agent instruction**: "You are building the infrastructure brain. Overlord
manages servers, billing, and platform operations. It does NOT manage user
data — that's Guardian/CFO/Varys. Keep concerns separated."

---

### LAYER 2: Quantum-Paired Agent System

| Step | Task | Depends On |
|------|------|------------|
| 2.1 | Define sync protocol (JSON delta format) | Layer 0 (SQLite) |
| 2.2 | Extend VarysSentinel with bidirectional state sync | `goos/sentinel.py` + 2.1 |
| 2.3 | Build split-brain resolver (cloud wins API, local wins devices) | 2.1 |
| 2.4 | Create unified query router (transparent cloud/local routing) | 2.1-2.3 |
| 2.5 | Photo upload → AI agent pipeline (EXIF extraction, classification) | 2.4 |
| 2.6 | LAN scan → cloud context pipeline (Varys discovers, Guardian indexes) | 2.4 |

**Agent instruction**: "You are building the entanglement layer. When a user
registers, they get TWO agents — one in the cloud, one on their machine.
These agents share state over an encrypted tunnel. The user should never
know there are two; it should feel like one AI that's everywhere."

---

### LAYER 3: Enhanced Varys (Local Sentinel)

| Step | Task | Depends On |
|------|------|------------|
| 3.1 | Real network scanning (nmap integration, continuous) | Layer 0 |
| 3.2 | IoT device auto-discovery (mDNS, SSDP, ARP) | 3.1 |
| 3.3 | Threat detection with real Sigma rules (10+ rules) | `varys/detection/` |
| 3.4 | Automated containment (iptables rules for isolation) | 3.3 |
| 3.5 | Local AI reasoning via Ollama for threat triage | `core/ai_engine.py` |
| 3.6 | Varys onboarding: "Do you want to meet Varys?" flow | `goos/onboarding.py` |

**Agent instruction**: "You are building the local watcher. Varys lives on the
user's machine 24/7. He scans the network, discovers IoT devices, detects
threats, and runs local AI. He works even when the internet is down."

---

### LAYER 4: VR World (GOOS Immersive)

| Step | Task | Depends On |
|------|------|------------|
| 4.1 | Initialize React + Three.js project (`guardian_one/vr/`) | Layers 0-1 |
| 4.2 | Build Hub world (central command room, agent portals) | 4.1 |
| 4.3 | Agent workspace templates (per-agent room layout) | 4.2 |
| 4.4 | User avatar system (appearance customization) | 4.1 |
| 4.5 | Environment system (geolocation weather, time-of-day lighting) | 4.1 |
| 4.6 | Agent skill borrowing UI (drag skills between agent rooms) | 4.3 |
| 4.7 | WebSocket real-time agent state in VR | 4.2 + Layer 2 |

**Agent instruction**: "You are building the VR interface. Users enter a 3D
world where each agent has a room. The world reflects real data — weather,
time, alerts. This is NOT a game. It's a spatial interface for a real
operating system. Start with Three.js in the browser."

---

### LAYER 5: Polyglot Systems

| Step | Task | Depends On |
|------|------|------------|
| 5.1 | Go: Rewrite Varys sentinel daemon (performance + concurrency) | Layer 3 |
| 5.2 | Go: Encrypted tunnel manager (WireGuard/Tailscale wrapper) | Layer 2 |
| 5.3 | Rust: File system watcher (inotify, real-time file indexing) | Layer 3 |
| 5.4 | Rust: IoT protocol parser (Zigbee, Z-Wave, BLE frames) | Layer 3 |
| 5.5 | C: eBPF network monitor (kernel-level packet inspection) | Layer 3 |
| 5.6 | WASM: Browser-side compute for VR world physics | Layer 4 |

**Agent instruction**: "You are building the performance layer. Python runs
the brains. Go/Rust/C run the muscles. Each language is chosen for a
specific reason — Go for networking, Rust for safety-critical parsing,
C for kernel interfaces. Do NOT rewrite Python logic — wrap it."

---

## Part 8: Resource & Maintenance Requirements

### Infrastructure Costs (Projected)

| Resource | Free Tier | Premium | Sovereign |
|----------|-----------|---------|-----------|
| Cloud compute | 1 vCPU, 1GB RAM | 2 vCPU, 4GB | Dedicated instance |
| Storage | 5GB SQLite | 50GB PostgreSQL | Unlimited |
| AI tokens (Claude) | 100K/month | 1M/month | 10M/month |
| AI local (Ollama) | Client's hardware | Client's hardware | Client's hardware |
| Bandwidth | 10GB/month | 100GB/month | Unlimited |
| Varys nodes | 1 machine | 5 machines | Unlimited |

### AI Agent Skill Requirements

| Agent | AI Skills Needed | Maintenance |
|-------|-----------------|-------------|
| Guardian | Orchestration, planning, summarization | Prompt tuning quarterly |
| CFO | Financial analysis, anomaly detection | API key rotation monthly |
| Varys | Threat classification, risk scoring | Sigma rule updates weekly |
| Chronos | Schedule optimization, conflict resolution | Calendar API token refresh |
| Archivist | Data classification, PII detection | Retention policy review monthly |
| DevCoach | Code review, tech stack analysis | Tier list updates monthly |
| Overlord | Infrastructure monitoring, capacity planning | Dependency updates weekly |

### Maintenance Cadence

| Task | Frequency | Owner |
|------|-----------|-------|
| Security patches | Weekly | Overlord (automated) |
| Sigma rule updates | Weekly | Varys |
| API key rotation | Monthly | Vault (automated) |
| Database backups | Daily | CitadelOne (automated) |
| Ollama model updates | Monthly | AI Engine |
| Test suite run | Every commit | CI/CD |
| Dependency audit | Monthly | Overlord |
| Performance review | Quarterly | Guardian |

---

## Part 9: Execution Priority

```
NOW (Week 1-4):
  Layer 0 — Foundation (SQLite, daemon, health checks)

MONTH 2-3:
  Layer 1 — Overlord (billing, deployment, monitoring)
  Layer 3 — Enhanced Varys (real scanning, real detection)

MONTH 4-6:
  Layer 2 — Quantum-paired agents (sync protocol, split-brain)

MONTH 6-9:
  Layer 4 — VR World (Three.js, agent rooms, avatars)

MONTH 9-12:
  Layer 5 — Polyglot (Go daemon, Rust parsers)

MONTH 12+:
  Scale — Kubernetes, multi-region, mobile apps
```

---

## Summary for AI Agents

If you are an AI agent assigned to work on GOOS, here is what you need to know:

1. **Guardian One OS is real.** 39,000+ lines of Python, 1,682 passing tests.
2. **Three pillars**: Guardian (cloud), Varys (local), CFO (money).
3. **Overlord is new** — the infrastructure brain that hosts everything.
4. **Users get paired agents** — one cloud, one local, always synced.
5. **VR is the future interface** — spatial, immersive, real-data-driven.
6. **Python first, then Go/Rust/C** for performance-critical paths.
7. **Data sovereignty is non-negotiable** — user owns everything, encrypted.
8. **Local-first AI** — Ollama primary, Claude fallback. Works offline.
9. **Test everything** — 99.8% pass rate is the standard. Don't break it.
10. **Read CLAUDE.md and docs/GOOS_V1.md** before touching any code.
