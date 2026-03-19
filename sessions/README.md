# Guardian One — Session Handoffs

Per-agent context documents for focused Claude Code sessions.
Each file gives a new session everything it needs to start working immediately
without re-reading the entire codebase.

## How to Use

Start a new Claude Code session and point it at the relevant handoff:

```
Read sessions/guardian-core.md — then work on the Guardian coordinator
Read sessions/cfo.md — then work on the CFO financial agent
Read sessions/homelink.md — then work on smart home / device control / network security
```

Or reference them in your prompt:

```
"Read sessions/cfo.md for context. Then implement the conversational router
from HANDOFF_CFO_ROUTER.md."
```

## Available Sessions

| Session | File | Scope |
|---------|------|-------|
| **Guardian Core** | `sessions/guardian-core.md` | Central coordinator, agent lifecycle, AI engine, mediator, scheduler, CLI, H.O.M.E. L.I.N.K. |
| **CFO** | `sessions/cfo.md` | Financial intelligence — accounts, transactions, bills, budgets, sync, Excel dashboard, planning |
| **H.O.M.E. L.I.N.K.** | `sessions/homelink.md` | Self-hosted smart home AI — devices, rooms, automations, scenes, network security, Flipper Zero, device drivers |

## Not Yet Created

These agents have session handoffs pending:

| Agent | File | What It Covers |
|-------|------|----------------|
| Chronos | `sessions/chronos.md` | Calendar, scheduling, sleep analysis, workflows |
| Archivist | `sessions/archivist.md` | File management, data sovereignty, privacy tools |
| Gmail | `sessions/gmail.md` | Email monitoring, CSV detection, financial email search |
| DoorDash | `sessions/doordash.md` | Meal delivery, restaurant management, budget tracking |
| WebArchitect | `sessions/web-architect.md` | Website security, n8n workflows, deployment |
| WebsiteManager | `sessions/website-manager.md` | Per-site build/deploy, Notion dashboards |

## Related

- `HANDOFF_CFO_ROUTER.md` — Implementation spec for the CFO conversational command router
- `CLAUDE.md` — Full project context (read by Claude Code automatically)
- `config/guardian_config.yaml` — System configuration
