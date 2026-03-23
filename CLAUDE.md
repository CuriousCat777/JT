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
│   ├── archivist.py            # File & data sovereignty
│   ├── cfo.py                  # Financial intelligence (Plaid, Empower, Rocket Money)
│   ├── cfo_dashboard.py        # Excel financial dashboards
│   ├── doordash.py             # Meal delivery coordination
│   ├── gmail_agent.py          # Email & inbox monitoring
│   ├── web_architect.py        # Website security & n8n deployment
│   ├── website_manager.py      # Per-site build/deploy pipelines
│   └── device_agent.py         # IoT/smart home device management & automation
├── core/                       # System infrastructure
│   ├── guardian.py              # Central coordinator
│   ├── base_agent.py           # Agent contract (BaseAgent ABC)
│   ├── daemon.py               # Headless daemon mode + health API (/health, /status, /metrics)
│   ├── logging.py              # Structured JSON logging with daily rotation
│   ├── mediator.py             # Cross-agent conflict resolution
│   ├── scheduler.py            # Agent scheduling
│   ├── sandbox.py              # Deployment testing
│   ├── evaluator.py            # Performance metrics
│   ├── audit.py                # Immutable audit logging
│   ├── security.py             # Access control
│   └── config.py               # Configuration management
├── integrations/               # External service connectors
│   ├── notion_sync.py          # Write-only Notion workspace sync
│   ├── notion_website_sync.py  # Per-site Notion dashboards
│   ├── n8n_sync.py             # n8n workflow automation
│   ├── financial_sync.py       # Plaid/Empower/Rocket Money
│   ├── calendar_sync.py        # Google Calendar
│   ├── gmail_sync.py           # Gmail API
│   ├── doordash_sync.py        # DoorDash API
│   └── privacy_tools.py        # VPN/privacy services
├── homelink/                   # H.O.M.E. L.I.N.K. — API infrastructure + smart home control
│   ├── gateway.py              # API gateway (TLS 1.3, rate limiting, circuit breakers)
│   ├── vault.py                # Encrypted credential storage (Fernet/PBKDF2)
│   ├── registry.py             # Integration catalog with threat models & rollback plans
│   ├── monitor.py              # API health monitoring, anomaly detection, weekly briefs
│   ├── devices.py              # Device inventory, room model, Flipper Zero profiles
│   └── automations.py          # Rule-based home automation engine (routines & scenes)
└── utils/                      # Shared utilities
config/
├── guardian_config.yaml        # Agent & system configuration
├── guardian-one.service        # systemd service unit for daemon mode
scripts/
├── setup.sh                    # Environment setup script
.github/workflows/
├── test.yml                    # CI pipeline (pytest on push/PR)
tests/                          # 878 pytest test cases
```

## Managed Websites

Two active web properties managed via `WebsiteManager` + `WebArchitect`:

| Domain | Type | Purpose |
|--------|------|---------|
| **drjeremytabernero.org** | Professional | Personal/professional site, CV, publications |
| **jtmdai.com** | Business | JTMD AI — AI solutions, services, case studies |

### Website CLI Commands
```bash
python main.py --websites              # Show all site status
python main.py --website-build all     # Build all sites
python main.py --website-build drjeremytabernero.org  # Build one site
python main.py --website-deploy all    # Deploy all sites
python main.py --website-sync          # Push dashboards to Notion
```

### Website Notion Integration
Each site gets its own Notion dashboard page under a "Website Management" parent,
showing build status, page inventory, security posture, and deploy history.
All data passes through the content classification gate (no PHI/PII ever leaves).

## Key Design Principles

1. **Data sovereignty** — User owns all data, encrypted at rest/transit
2. **Write-only Notion** — Push operational data only, never read for decisions
3. **Content gate** — PHI/PII patterns blocked before any external sync
4. **Audit everything** — Immutable log of all agent actions
5. **On-demand credentials** — Tokens loaded from Vault per-request, never cached
6. **Agent isolation** — Each agent has defined allowed_resources

## H.O.M.E. L.I.N.K.

Home Operations Management Engine: Linked Infrastructure & Network Kernel.
Two systems working as one:

### API Infrastructure
Every external API call from any agent routes through the Gateway with TLS enforcement,
rate limiting, circuit breakers, and full audit logging. Credentials live in the Vault
(Fernet-encrypted, PBKDF2-derived keys). Each integration has a threat model and
rollback procedure in the Registry. The Monitor detects anomalies and generates
weekly security briefs.

### Smart Home Control
The DeviceAgent manages Jeremy's physical devices (cameras, smart plugs, lights,
blinds, Samsung TV, vehicle, Flipper Zero) via the device inventory in `devices.py`.
Automation rules in `automations.py` drive schedule-based routines (wake/sleep/leave/arrive),
occupancy-triggered actions, solar events, and named scenes (Movie Mode, Focus Mode,
Away Mode, Goodnight). All device actions are audited and reversible.

### Managed Device Ecosystem
- TP-Link Kasa/Tapo smart plugs (local LAN API)
- Philips Hue lights (Zigbee via Hue Bridge)
- Govee lights (LAN UDP or cloud API)
- Ryse SmartShade blinds (BLE/WiFi)
- Samsung The Frame 65" (IoT VLAN isolated, hardened)
- Security cameras (RTSP/ONVIF)
- Flipper Zero (sub-GHz, NFC, IR, BLE security tool)
- Connected vehicle (OBD-II + manufacturer API)

## Security Architecture

- **Vault**: Fernet-encrypted credential storage with PBKDF2 key derivation, per-credential scoping, rotation tracking
- **Gateway**: TLS 1.3 enforcement, rate limiting, circuit breakers, retry with backoff for all external calls
- **Registry**: Every integration has a threat model (top 5 risks) and rollback procedure
- **Device Security**: Network segmentation (IoT VLAN), firmware tracking, UPnP enforcement, security audits
- **Content Classification**: Regex-based PHI/PII scanner blocks sensitive data from sync
- **Audit Log**: Append-only, severity-tagged, immutable records

## Configuration

Primary config: `config/guardian_config.yaml`
Environment: `.env` (NOTION_TOKEN, API keys, etc.)

## Running Tests

```bash
pytest tests/ -v                       # All tests (878)
pytest tests/test_daemon.py            # Daemon + health API tests
pytest tests/test_logging.py           # Structured logging tests
pytest tests/test_website_manager.py   # Website manager tests
pytest tests/test_notion_website_sync.py  # Notion website sync tests
pytest tests/test_web_architect.py     # WebArchitect tests
```

## Common CLI Commands

```bash
python main.py                         # Run all agents once
python main.py --schedule              # Start agent scheduler
python main.py --daemon                # Run as background daemon (headless + health API)
python main.py --daemon --daemon-port 5200  # Custom health API port
python main.py --dashboard             # Generate CFO Excel dashboard
python main.py --sync                  # Continuous financial sync
python main.py --calendar-sync         # Sync Google Calendar
python main.py --gmail                 # Gmail inbox status
python main.py --websites              # Website management
python main.py --homelink              # H.O.M.E. L.I.N.K. status
python main.py --brief                 # Weekly security brief
python main.py --sandbox               # Sandbox deployment
```

## Development Notes

- Python 3.11+, no Docker yet (on roadmap)
- All agents extend `BaseAgent` (core/base_agent.py) with initialize/run/report
- Tests use fake providers (no real API calls)
- Config loaded via `load_config()` from core/config.py
- Multi-device: This CLAUDE.md carries full context across machines via git

## Cross-Device Setup

Clone on any machine and Claude Code will understand the project:
```bash
git clone <repo-url> ~/JT
cd ~/JT
# Claude Code reads this CLAUDE.md automatically
```

Both machines (current + ROG X 64GB) share context through this repo.
Always pull latest before starting work on a new device.
