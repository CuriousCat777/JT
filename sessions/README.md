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
Read sessions/chronos.md — then work on calendar & scheduling
Read sessions/archivist.md — then work on data sovereignty & privacy
Read sessions/gmail.md — then work on email intelligence
Read sessions/doordash.md — then work on meal delivery coordination
Read sessions/web.md — then work on websites, n8n, security, Notion dashboards
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
| **Chronos** | `sessions/chronos.md` | Calendar, Google Calendar sync, sleep analysis, routines, workflows, Epic FHIR |
| **Archivist** | `sessions/archivist.md` | File management, data sovereignty, NordVPN, DeleteMe, retention policies |
| **Gmail** | `sessions/gmail.md` | Email monitoring, Rocket Money CSV detection, financial email search |
| **DoorDash** | `sessions/doordash.md` | Meal delivery, restaurant management, DoorDash Drive API, budget tracking |
| **Web Properties** | `sessions/web.md` | WebArchitect + WebsiteManager + n8n + Notion dashboards |

## Related

- `HANDOFF_CFO_ROUTER.md` — Implementation spec for the CFO conversational command router
- `CLAUDE.md` — Full project context (read by Claude Code automatically)
- `config/guardian_config.yaml` — System configuration
