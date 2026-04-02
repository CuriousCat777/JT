# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Guardian One is a **multi-agent AI orchestration platform** for personal life management,
built for Jeremy Paulo Salvino Tabernero (timezone: America/Chicago). It coordinates
autonomous agents that handle finance, scheduling, email, meals, websites, smart home,
and data sovereignty — all with encryption, audit trails, and zero data exploitation.

## Build & Test Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_guardian.py -v

# Run a single test
pytest tests/test_guardian.py::TestGuardianOne::test_register_agent -v

# Run the system (all agents once)
python main.py

# Run a single agent
python main.py --agent chronos

# Interactive chat UI (Rich terminal)
python main.py --chat

# Dev panel (Flask web UI on port 5100)
python main.py --devpanel
```

Async tests use `pytest-asyncio` with `asyncio_mode = "auto"` (configured in pyproject.toml).
Tests use fake providers — no real API calls are made.

## Architecture

### Execution Flow

`main.py` → parses 30+ CLI flags via argparse → instantiates `GuardianOne` coordinator →
registers all agents via `_build_agents()` → dispatches to the requested command.

### Core Layers

- **`GuardianOne`** (`core/guardian.py`): Central coordinator. Boots agents, enforces access
  control, mediates conflicts, produces daily summaries. Owns the AI engine, Gateway, Vault,
  Registry, and Monitor instances.

- **`BaseAgent`** (`core/base_agent.py`): Abstract base class. Every agent implements
  `initialize()`, `run()` → `AgentReport`, and `report()`. Agents get AI reasoning via
  `self.think(prompt)` / `self.think_quick(prompt)` — the AI engine is injected post-registration.

- **`AIEngine`** (`core/ai_engine.py`): Dual-provider LLM backend. Primary: Ollama (local).
  Fallback: Anthropic Claude API. Handles provider selection, failover, and per-agent
  conversation memory.

- **`CommandRouter`** (`core/command_router.py`): Natural-language intent router for the CFO
  agent. Keyword-based matching → CFO method dispatch → optional AI summary enhancement.
  Works fully without an AI backend.

### Agent Pattern

All agents live in `guardian_one/agents/`. Each extends `BaseAgent` and follows the lifecycle:
`__init__` → `initialize()` → `run()` → `report()` → `shutdown()`.

To add a new agent: copy `guardian_one/templates/agent_template.py`, implement the three
abstract methods, register in `config/guardian_config.yaml`, wire into `main.py:_build_agents()`,
and add tests.

### H.O.M.E. L.I.N.K. (`guardian_one/homelink/`)

Two systems in one:

1. **API Infrastructure**: All external API calls route through `Gateway` (TLS 1.3, rate
   limiting, circuit breakers). Credentials in `Vault` (Fernet/PBKDF2). Each integration
   has a threat model in `Registry`. `Monitor` detects anomalies and generates weekly briefs.

2. **Smart Home Control**: `DeviceAgent` manages physical devices via `DeviceRegistry`
   (devices.py). `AutomationEngine` (automations.py) drives schedule-based routines,
   occupancy triggers, solar events, and named scenes (Movie, Focus, Away, Goodnight).

### Integrations (`guardian_one/integrations/`)

External service connectors. Each is a standalone module consumed by its corresponding agent.
Notion integration is **write-only** — push operational data, never read for decisions.
All syncs pass through a content classification gate that blocks PHI/PII patterns.

### Web UI (`guardian_one/web/`)

Flask-based dev panel (`app.py`). Mirrors `main.py`'s agent wiring. Runs on port 5100.

## Key Design Rules

1. **Data sovereignty** — User owns all data, encrypted at rest/transit
2. **Write-only Notion** — Push only, never read for decisions
3. **Content gate** — PHI/PII regex scanner blocks sensitive data before any external sync
4. **Audit everything** — Immutable append-only log of all agent actions (`core/audit.py`)
5. **On-demand credentials** — Tokens loaded from Vault per-request, never cached in memory
6. **Agent isolation** — Each agent has `allowed_resources` defined in config

## Configuration

- **Primary config**: `config/guardian_config.yaml` — agents, AI engine, services, security
- **Environment**: `.env` — API keys (`NOTION_TOKEN`, `ANTHROPIC_API_KEY`, etc.)
- **Config loading**: `core/config.py:load_config()` merges YAML + env vars into dataclasses
  (`GuardianConfig`, `AgentConfig`, `AIEngineConfig`, `SecurityConfig`)

## Managed Websites

| Domain | Status | Type |
|--------|--------|------|
| drjeremytabernero.org | down | Professional/CV |
| jtmdai.com | live | Business (JTMD AI) |

Managed via `WebsiteManager` + `WebArchitect` agents. Each site has a Notion dashboard.

## CLI Quick Reference

```bash
python main.py --schedule          # Start agent scheduler
python main.py --dashboard         # CFO Excel dashboard
python main.py --sync              # Continuous financial sync
python main.py --gmail             # Gmail inbox status
python main.py --calendar-sync     # Sync Google Calendar
python main.py --websites          # All website status
python main.py --website-build all # Build all sites
python main.py --homelink          # H.O.M.E. L.I.N.K. status
python main.py --devices           # Smart home dashboard
python main.py --scene movie       # Activate a scene
python main.py --brief             # Weekly security brief
python main.py --notion-sync       # Full Notion workspace sync
python main.py --security-review   # Security remediation review
python main.py --connector-audit   # Claude connector attack surface audit
```
