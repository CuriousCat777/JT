# Guardian One Operating System V1.0 (GOOS)

## Consolidated Architecture Specification

**Version**: 1.0
**Date**: 2026-04-06
**Author**: Jeremy Paulo Salvino Tabernero

---

## 1. Vision

GOOS is a **multi-tenant AI operating system** that gives every user a personal
AI command center. It starts as a web platform, installs locally on Linux
desktops and phones, and provides three core entities:

| Entity | Role | Where It Lives |
|--------|------|----------------|
| **Guardian** | Central command AI — online coordinator, cloud reasoning | Cloud (GOOS servers) |
| **Varys** | Local sentinel — always-on, manages physical world, IoT, LAN security | User's local machines (24/7) |
| **CFO** | Financial intelligence — bank accounts, budgets, net-worth tracking | Cloud (Guardian-managed) |

**Guardian is the brain online. Varys is the brain on your machines.**

Together they form a sovereign AI operating system where the user owns their data,
controls their network, and has AI agents working for them around the clock.

---

## 2. User Journey

### Phase 1: Registration
```
User visits GOOS website (e.g., goos.jtmdai.com)
  → Site presents "Register for Guardian One"
  → Client provides account identification (email, name)
  → CAPTCHA / human verification (hCaptcha, no Google)
  → Email verification sent
  → Account created with unique client_id
  → Encryption keys generated (client-side)
```

### Phase 2: Onboarding — Meet Guardian
```
First login → Onboarding wizard begins
  → "Welcome to Guardian One Operating System"
  → Interactive introduction to the GOOS environment
  → Guardian introduces itself:
     "I am Guardian. I will be your central command AI agent.
      I coordinate everything online — your finances, your schedule,
      your email, your websites. Think of me as your executive assistant
      who never sleeps."
  → File exchange interface offered (upload documents, photos, records)
  → Chat box opens — first conversation with Guardian
  → Guardian explains the two-agent concept:
     "You'll work with two AI agents. Me — I handle the cloud.
      And Varys — he handles your local world."
```

### Phase 3: Meet the CFO
```
Guardian introduces the CFO:
  → "This is the CFO. He manages your money."
  → "What you tell him will be shared with me — we work together."
  → CFO requests bank information (Plaid Link integration)
  → Budget preferences captured
  → Financial profile established
  → "The CFO will monitor your accounts, track your net worth,
     and alert you to anything unusual."
```

### Phase 4: Meet Varys — Install GOOS Locally
```
Guardian introduces Varys:
  → "This is Varys. He is your local agent."
  → "Varys will live on your computers — always available, 24/7."
  → "He manages your physical world: IoT devices, home network,
     local security. He is my collaborator."
  → Request permission to install GOOS on local machines
  → Start with Linux machines (primary target)
  → Install script provided:
     curl -sSL https://goos.jtmdai.com/install | bash
  → Varys installs as a systemd service
  → Varys discovers local network, IoT devices
  → H.O.M.E. L.I.N.K. activates — IoT interface layer
  → Varys establishes secure tunnel back to Guardian (Tailscale/WireGuard)
```

### Phase 5: Fully Onboarded
```
All agents active:
  → Guardian (cloud) — central command, online
  → Varys (local) — physical world, IoT, LAN, always-on
  → CFO (cloud) — financial intelligence
  → Additional agents activated as needed:
     - Chronos (scheduling)
     - Archivist (data sovereignty)
     - Gmail Agent (email)
     - WebArchitect (websites)
     - DoorDash (meals)
     - DevCoach (developer mentoring)
```

---

## 3. Architecture

### 3.1 System Topology

```
                    ┌──────────────────────────────────┐
                    │        GOOS Cloud Platform        │
                    │  ┌───────────┐  ┌──────────────┐ │
                    │  │ Guardian  │  │   CFO Agent   │ │
                    │  │ (Central  │  │  (Financial   │ │
                    │  │  Command) │  │  Intelligence)│ │
                    │  └─────┬─────┘  └──────┬───────┘ │
                    │        │               │         │
                    │  ┌─────┴───────────────┴───────┐ │
                    │  │    Agent Orchestrator        │ │
                    │  │  Chronos | Archivist | Gmail │ │
                    │  │  WebArch | DoorDash | Coach  │ │
                    │  └─────────────┬────────────────┘ │
                    │               │                   │
                    │  ┌────────────┴────────────────┐  │
                    │  │   GOOS API Gateway           │  │
                    │  │   Auth | Rate Limit | TLS    │  │
                    │  └────────────┬────────────────┘  │
                    └───────────────┼───────────────────┘
                                   │
                          Encrypted Tunnel
                        (Tailscale/WireGuard)
                                   │
            ┌──────────────────────┼──────────────────────┐
            │          User's Local Machine(s)             │
            │                                              │
            │  ┌────────────────────────────────────────┐  │
            │  │              VARYS                      │  │
            │  │         Local Sentinel                  │  │
            │  │                                         │  │
            │  │  ┌──────────┐  ┌────────────────────┐  │  │
            │  │  │ Security │  │   H.O.M.E. L.I.N.K │  │  │
            │  │  │ Monitor  │  │   IoT Interface     │  │  │
            │  │  │ • Sigma  │  │   • Device Control  │  │  │
            │  │  │ • Anomaly│  │   • Scenes/Automate │  │  │
            │  │  │ • Risk   │  │   • Network Monitor │  │  │
            │  │  └──────────┘  └────────────────────┘  │  │
            │  │                                         │  │
            │  │  ┌──────────┐  ┌────────────────────┐  │  │
            │  │  │ Vault    │  │   Ollama (Local AI) │  │  │
            │  │  │ (Local   │  │   Privacy-first     │  │  │
            │  │  │  Creds)  │  │   Reasoning         │  │  │
            │  │  └──────────┘  └────────────────────┘  │  │
            │  └────────────────────────────────────────┘  │
            └──────────────────────────────────────────────┘
```

### 3.2 The Three Pillars

#### Pillar 1: Guardian (Cloud Coordinator)
- **Existing code**: `guardian_one/core/guardian.py`
- Manages all cloud-side agents
- Processes data that requires internet (email, finance APIs, calendar sync)
- Provides the web interface and API
- Communicates with Varys over encrypted tunnel

#### Pillar 2: Varys (Local Sentinel)
- **Existing code**: `guardian_one/varys/agent.py` + `guardian_one/homelink/`
- Runs as a daemon on user's local machines (systemd service)
- Manages IoT devices through H.O.M.E. L.I.N.K.
- Provides local AI via Ollama (no internet needed)
- Network security monitoring and threat detection
- Always available — even when internet is down
- **Consolidation**: Varys absorbs all Homelink functionality as its interface layer

#### Pillar 3: CFO (Financial Intelligence)
- **Existing code**: `guardian_one/agents/cfo.py`
- Bank account connections via Plaid
- Net-worth tracking, budget management
- Bill alerts, spending analysis
- Reports to Guardian, data encrypted in Vault

### 3.3 Varys + Homelink Consolidation

**Before** (fragmented):
```
varys/          → Security only (skeleton)
homelink/       → IoT only (separate system)
agents/device_agent.py → Device management (unregistered)
agents/iot_sentinel.py → Network monitoring (unregistered)
```

**After** (consolidated):
```
varys/                          → The local sentinel
  ├── agent.py                  → VarysAgent (BaseAgent) — main entry point
  ├── sentinel.py               → VarysSentinel — daemon/service manager
  ├── homelink/                 → H.O.M.E. L.I.N.K. (Varys's IoT interface)
  │   ├── controller.py         → Device control
  │   ├── devices.py            → Device registry
  │   ├── automations.py        → Scenes and automations
  │   └── drivers/              → Hardware-specific drivers
  ├── detection/                → Security detection (existing)
  ├── response/                 → Automated response (existing)
  ├── brain/                    → LLM triage (existing)
  ├── network/                  → Network monitoring + scanner
  └── tunnel.py                 → Secure tunnel to Guardian
```

**Key change**: Varys is no longer just security. Varys is the **entire local
operating system**. Homelink is Varys's interface to the physical world.

---

## 4. Multi-Tenant Data Model

### 4.1 Client Model

```python
class GOOSClient:
    client_id: str          # UUID, immutable
    email: str              # Verified email
    display_name: str
    created_at: datetime
    tier: ClientTier        # FREE | PREMIUM | SOVEREIGN
    status: ClientStatus    # PENDING | ONBOARDING | ACTIVE | SUSPENDED
    onboarding_step: str    # Current onboarding phase
    encryption_key_hash: str  # Client-side encryption key hash
    varys_nodes: list[VarysNode]  # Registered local installations
    agents_enabled: list[str]     # Which agents are active
```

### 4.2 Client Tiers

| Tier | Price | Features |
|------|-------|----------|
| **Free** | $0 | Guardian + Varys (local only), basic IoT, community support |
| **Premium** | TBD | Full agent suite, cloud sync, CFO, priority support |
| **Sovereign** | TBD | Dedicated instance, custom agents, SLA, full data export |

**Philosophy** (like OpenLaw): Eventually free for everyone. Distribution is
limited for products like this, so premium tiers fund development. Users can
always detach from the internet and work with Varys alone.

### 4.3 Offline Mode

Users can choose to **detach from the internet** and work exclusively with Varys:
- Varys continues operating locally with Ollama for AI
- IoT management continues (H.O.M.E. L.I.N.K. is local)
- Security monitoring continues (LAN-only)
- No cloud sync, no Guardian, no CFO
- User can reconnect at any time — Varys syncs queued data back to Guardian

---

## 5. Onboarding Agent Flow

### 5.1 The Onboarding Conversation

```
GUARDIAN: Welcome to Guardian One Operating System.
          I'm Guardian — your central command AI.
          Let me show you around.

          [Interactive tour of GOOS dashboard]

GUARDIAN: You'll work with two agents. Me — I handle the cloud.
          And Varys — he handles your local world.

          But first, let me introduce you to someone who will
          help manage your finances.

          [CFO agent activates]

CFO:      Hello. I'm the CFO.
          I'll need some information to get started.
          What you share with me will be shared with Guardian —
          we work as a team.

          Would you like to connect your bank accounts?
          [Plaid Link integration]

          What are your monthly budget goals?
          [Budget setup wizard]

GUARDIAN: Good. Now let's set up your local agent.

          Varys will live on your computers. He's always available,
          24/7. He manages your IoT devices, your home network,
          and keeps your local environment secure.

          He'll be my collaborator — I work online, he works locally.

          [Install prompt for Linux]
          curl -sSL https://goos.jtmdai.com/install | bash

          [Varys installation begins]

VARYS:    Systems online. I've detected your local network.
          [Network scan results]
          [IoT device discovery]

          I'll be here whenever you need me.
          Guardian and I will keep you covered.

GUARDIAN: You're fully onboarded.
          Here's what's active:
          - Me (Guardian) — central command, online
          - CFO — managing your finances
          - Varys — your local sentinel, always on

          From here, we can activate more agents:
          - Chronos (scheduling)
          - Archivist (data sovereignty)
          - And more...

          What would you like to do first?
```

---

## 6. Technical Implementation Plan

### 6.1 What Exists Today (Reuse)

| Component | File(s) | Status | GOOS Role |
|-----------|---------|--------|-----------|
| GuardianOne coordinator | `core/guardian.py` | Production-ready | Cloud coordinator per client |
| BaseAgent contract | `core/base_agent.py` | Production-ready | All agents inherit |
| AI Engine | `core/ai_engine.py` | Production-ready | Reasoning backbone |
| Vault | `homelink/vault.py` | Production-ready | Per-client credential storage |
| Gateway | `homelink/gateway.py` | Production-ready | API gateway |
| Audit | `core/audit.py` | Production-ready | Per-client audit trails |
| Security/Access | `core/security.py` | Production-ready | Multi-tenant RBAC |
| Mediator | `core/mediator.py` | Production-ready | Cross-agent conflict resolution |
| CFO Agent | `agents/cfo.py` | 75% complete | Financial intelligence |
| VarysAgent | `varys/agent.py` | 60% complete | Local sentinel core |
| Homelink modules | `homelink/*.py` | 40-100% varies | Varys's IoT interface |
| Citadel | `core/citadel.py` | Working | Backup/restore |
| Flask web panel | `web/app.py` | 70% complete | GOOS web dashboard basis |
| MCP server | `mcp_server.py` | Production-ready | Claude integration |
| Config system | `core/config.py` | Production-ready | Per-client config |

### 6.2 What Needs Building

| Component | Priority | Description |
|-----------|----------|-------------|
| `goos/client.py` | P0 | Multi-tenant client model |
| `goos/registration.py` | P0 | Account creation + verification |
| `goos/onboarding.py` | P0 | Guided onboarding flow |
| `goos/auth.py` | P0 | JWT authentication |
| `goos/api.py` | P0 | REST API for GOOS platform |
| `varys/sentinel.py` | P1 | Varys daemon/service manager |
| `varys/tunnel.py` | P1 | Secure tunnel to Guardian |
| `goos/installer.py` | P1 | Linux installer script |
| `goos/tiers.py` | P2 | Tier management + billing |

### 6.3 Files Archived (Legacy)

Moved to `legacy/` — iteration snapshots no longer needed in active codebase:
```
guardian_system.py      → legacy/
guardian_system_1.py    → legacy/
guardian_system_2.py    → legacy/
guardian_system_3.py    → legacy/
guardian_system_4.py    → legacy/
guardian_lesson_2.py    → legacy/
guardian_lesson_2_1.py  → legacy/
guardian_lesson_3.py    → legacy/
guardian_agent_setup.py → legacy/
guardian_agent_setup_1.py → legacy/
guardian_test.py        → legacy/
guardian_test_1.py      → legacy/
guardian_test_2.py      → legacy/
```

---

## 7. Agent Registry (Canonical)

### Cloud Agents (run with Guardian)

| Agent | Status | Registered In |
|-------|--------|---------------|
| Chronos | Active | main.py, mcp_server.py |
| CFO | Active | main.py, mcp_server.py |
| Archivist | Active | main.py, mcp_server.py |
| Gmail | Active | main.py, mcp_server.py |
| WebArchitect | Active | main.py, mcp_server.py |
| DoorDash | Active | main.py, mcp_server.py |
| DevCoach | Active | main.py |

### Local Agent (runs with Varys)

| Agent | Status | Registered In |
|-------|--------|---------------|
| Varys | Active | main.py, mcp_server.py |
| DeviceAgent | Subsumed | → Varys/Homelink |
| IoTSentinel | Subsumed | → Varys/Network |

### Support Components (not BaseAgent)

| Component | File | Used By |
|-----------|------|---------|
| CFO Dashboard | `agents/cfo_dashboard.py` | CFO |
| Website Manager | `agents/website_manager.py` | WebArchitect |
| Teleprompter | `agents/teleprompter.py` | Standalone |

---

## 8. Security Architecture

### Per-Client Isolation
- Each client gets their own Vault (encryption key derived from their passphrase)
- Each client gets their own audit trail
- Agent access policies scoped per client
- Varys nodes authenticate via client certificate

### Data Flow Rules
1. **Client data never leaves their Vault unencrypted**
2. **Varys-to-Guardian tunnel is always encrypted (WireGuard/Tailscale)**
3. **PHI/PII content gate blocks sensitive data from external sync**
4. **Offline mode: zero data leaves the local machine**

### Access Levels (Extended for Multi-Tenant)

| Level | Who | Access |
|-------|-----|--------|
| OWNER | Client | Full access to their data |
| GUARDIAN | Guardian coordinator | System-wide for that client |
| AGENT | Subordinate agents | Scoped per agent config |
| VARYS | Local sentinel | Full local access, scoped cloud access |
| READONLY | Auditors | Read-only audit logs |
| ADMIN | GOOS operators | Platform management (never client data) |

---

## 9. Deployment Strategy

### Phase 1: MVP (Current → 3 months)
- GOOS web registration portal
- Guardian cloud with basic onboarding
- CFO agent with Plaid integration
- Varys installer for Linux (Ubuntu/Debian first)
- Single-tenant proof of concept (Jeremy's instance)

### Phase 2: Beta (3-6 months)
- Multi-tenant isolation
- Client dashboard
- Varys systemd service with auto-updates
- H.O.M.E. L.I.N.K. device discovery
- Offline mode

### Phase 3: Launch (6-12 months)
- Public registration
- Free + Premium tiers
- Mobile app (Android first via Linux compatibility)
- Full agent suite available
- Community plugins

---

## 10. Relationship Map

```
                    GUARDIAN
                   (The Brain Online)
                  /       |        \
                 /        |         \
              CFO      Chronos    Archivist
           (Money)    (Time)     (Data)
              |          |          |
              +----------+----------+
                         |
                    GOOS API GATEWAY
                         |
                    ENCRYPTED TUNNEL
                         |
                      VARYS
                 (The Brain Locally)
                  /       |        \
                 /        |         \
          H.O.M.E.    Security    Network
          L.I.N.K.    Monitor     Scanner
         (IoT/Home)  (Threats)   (LAN Watch)
              |          |          |
              +----------+----------+
                         |
                    LOCAL MACHINE
                   (Always Available)
```

---

## Summary

GOOS V1.0 consolidates all fragmented iterations into one clear system:

1. **Guardian** = cloud AI coordinator (exists, production-ready)
2. **Varys** = local sentinel + Homelink IoT (consolidating, 60% → target 100%)
3. **CFO** = financial intelligence (exists, 75% complete)
4. **Registration + Onboarding** = new (being built)
5. **Multi-tenant model** = new (being built)
6. **Legacy files** = archived to `legacy/`

The starting vector is clear: a user registers, meets Guardian, meets CFO,
installs Varys, and has a fully sovereign AI operating system.
