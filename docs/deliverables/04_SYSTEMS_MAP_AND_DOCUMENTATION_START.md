# Guardian One — Systems Mapping & Documentation Starter

**Date started:** 2026-04-02  
**Owner:** Jeremy Paulo Salvino Tabernero  
**Purpose:** Create a living, audit-friendly map of all systems, integrations, and deployment surfaces.

---

## 1) What this document is

This is a **starter system map** that combines:
- The current Guardian One codebase architecture.
- The active external deployment footprint visible in the Cloudflare Workers & Pages dashboard screenshot.
- A repeatable process to keep documentation current as systems change.

This file is intended to become the canonical "where everything is" reference.

---

## 2) Current system topology (high level)

### Core orchestration
- `main.py` is the CLI/operator entrypoint.
- `guardian_one/core/` contains runtime control plane components:
  - Guardian coordinator
  - scheduler
  - security/access controls
  - audit and evaluation

### Domain agents
- `guardian_one/agents/` contains functional agents:
  - CFO
  - Chronos
  - Archivist
  - GmailAgent
  - DoorDash
  - WebArchitect
  - WebsiteManager
  - DeviceAgent

### External integration layer
- `guardian_one/integrations/` contains provider adapters for:
  - calendar, finance, Gmail, Notion, n8n, DoorDash, privacy tools, and Ollama.

### Service hardening layer (H.O.M.E. L.I.N.K.)
- `guardian_one/homelink/` provides:
  - gateway controls
  - encrypted vault
  - registry/threat-model catalog
  - monitoring and automation building blocks

### Operations & tests
- `config/guardian_config.yaml` drives config.
- `tests/` provides functional/system verification coverage.
- `docs/` contains governance, security, and deliverable documents.

---

## 3) External deployment footprint (Cloudflare Workers & Pages)

From the provided dashboard screenshot, the following applications are visible and should be treated as managed assets pending verification:

| App name | Type (inferred) | Domain/route shown | Last modified shown | Notes |
|---|---|---|---|---|
| dry-sea-a625 | Worker | `dry-sea-a625.jeremytabernero.workers.dev` | ~3h ago | 1 binding shown |
| fancy-forest-bf45 | Worker | `fancy-forest-bf45.jeremytabernero.workers.dev` | ~3h ago | 1 binding shown |
| guardian-one | Pages | `guardian-one.pages.dev` | ~15h ago | "No Git connection" shown |
| drjeremytabernero | Pages | `drjeremytabernero.pages.dev` | ~16h ago | "No Git connection" shown |
| jtcommand-one | Worker | `jtmdai.com/hospitalist` | ~19h ago | 3 bindings shown |
| guardian-vault | Worker | `jtmdai.com/vault*` | ~20h ago | 1 binding shown |
| long-smoke-da3d | Worker | `www.drjeremytabernero.org` + other routes | ~38d ago | 0 bindings shown |
| empty-darkness-2ec2 | Worker | `jtmdai.com` + other routes | ~38d ago | 0 bindings shown |

> **Verification note:** this section is screenshot-derived; execute `wrangler` inventory commands next to convert inferred values into authoritative infrastructure records.

---

## 4) System map register (starter)

Use this register as the master inventory table. Populate/maintain all rows.

| System ID | System | Layer | Owner | Environment(s) | Data classification | Auth method | Dependencies | SLA/SLO | Logging source | Runbook link | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| SYS-CORE-001 | Guardian CLI/runtime | Core | Jeremy | local, server | Internal operational | local credential + vault | Python runtime, config, vault | TBD | local logs + audit | TBD | Active |
| SYS-AGENT-001 | CFO Agent | Agent | Jeremy | local, server | Financial sensitive | vault-backed tokens | Plaid/financial connectors | TBD | audit + agent report | TBD | Active |
| SYS-AGENT-002 | Chronos Agent | Agent | Jeremy | local, server | Personal schedule | OAuth tokens | Google Calendar | TBD | audit + agent report | TBD | Active |
| SYS-AGENT-003 | WebsiteManager/WebArchitect | Agent | Jeremy | local + cloud | Public web + ops metadata | API token | Cloudflare, Notion, n8n | TBD | deploy/audit logs | TBD | Active |
| SYS-CF-001 | guardian-one.pages.dev | Cloudflare Pages | Jeremy | prod (?) | Public web | Cloudflare auth | Cloudflare DNS/routing | TBD | Cloudflare logs | TBD | Verify |
| SYS-CF-002 | drjeremytabernero.pages.dev | Cloudflare Pages | Jeremy | prod (?) | Public web | Cloudflare auth | Cloudflare DNS/routing | TBD | Cloudflare logs | TBD | Verify |
| SYS-CF-003 | guardian-vault worker route | Cloudflare Worker | Jeremy | prod (?) | Sensitive endpoint | Cloudflare auth + app auth | Worker bindings/secrets | TBD | Worker analytics | TBD | Verify |

---

## 5) Documentation process (recommended cadence)

### Weekly
1. Refresh infrastructure inventory (Cloudflare apps/routes/bindings/secrets list).
2. Reconcile inventory against this register.
3. Note adds/removes/renames in a changelog section.

### Monthly
1. Validate ownership and on-call/responsible person fields.
2. Validate data classification per system.
3. Confirm runbook links and incident response readiness.

### Per release
1. Update dependency graph (new integration, auth change, route change, secret changes).
2. Record risk deltas (new external surface, new PII/PHI handling risk).
3. Confirm tests and observability for changed systems.

---

## 6) Immediate next actions (documentation sprint)

1. **Authoritative Cloudflare export**
   - Capture full Workers/Pages inventory from CLI/API.
   - Export routes, bindings, env vars/secrets metadata, and deployment history summary.

2. **Map repo module → runtime service**
   - For each agent/integration module, document:
     - trigger mode (manual/scheduled/event)
     - read/write systems
     - output artifacts
     - failure mode and fallback

3. **Create runbooks folder**
   - Add `docs/runbooks/` with one file per critical system:
     - startup
     - health checks
     - rollback
     - incident triage

4. **Add ownership & criticality tags**
   - Tag every row in register with `critical`, `important`, or `supporting`.

5. **Add architecture diagram source file**
   - Add a Mermaid or draw.io source committed to repo for versioned updates.

---

## 7) Suggested supporting files to add next

- `docs/systems/SYSTEM_INVENTORY.csv`
- `docs/systems/SYSTEM_DEPENDENCY_MAP.md`
- `docs/runbooks/cloudflare_workers_pages.md`
- `docs/runbooks/guardian_core_runtime.md`
- `docs/changelog/SYSTEMS_CHANGELOG.md`

---

## 8) Definition of done for this mapping effort

The mapping effort is considered baseline-complete when:
- 100% of deployed systems are listed with owner, auth, dependencies, and runbook.
- Every external endpoint has data classification and risk notes.
- Every critical system has a tested recovery/rollback procedure.
- The system map, system register, and related docs are updated in every infra-affecting PR.

