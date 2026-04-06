# Guardian One — Session Handoff

**Date**: 2026-04-06
**Branch**: `claude/daemon-health-check-api-UeglO`
**Tests**: 913/913 passing
**Last commit**: `4f9f8d7` — Fix 13 issues from PR review

---

## What Was Built This Session

### 1. Archivist v2 — Central Telemetry System
Upgraded the Archivist from a simple file manager into the central nervous system:
- **TelemetryHub** (`archivist/telemetry.py`) — cross-system JSONL event logging with rotation
- **TechDetector** (`archivist/techdetect.py`) — auto-detect new tech, persist registry, flag for review
- **CloudSync** (`archivist/cloudsync.py`) — multi-cloud backup (local, Cloudflare R2, GitHub)
- **FileOrganizer** (`archivist/file_organizer.py`) — auto-categorize by keyword/extension, cleanup rules
- **AccountManager** (`archivist/account_manager.py`) — unified account tracker, password health scoring
- **PasswordSync** (`archivist/password_sync.py`) — 1Password/Bitwarden CLI metadata audit
- **KnowledgeExporter** (`archivist/knowledge_export.py`) — Markdown docs for Open WebUI RAG

All subsystems have persistence (JSON on disk) and survive restarts.

### 2. Infrastructure
- `.mcp.json` — 5 MCP servers (GitHub, filesystem, memory, fetch, SQLite)
- `.claude/settings.json` — permissions + pre-commit test hook
- `Dockerfile` — Python 3.11-slim container
- `docker-compose.yml` — Guardian + Ollama + Open WebUI (+ optional Wazuh)

### 3. PR Review Fixes (13 issues)
Fixed all actionable review comments from PR #10:
- **Security**: daemon health binds 127.0.0.1, web message validation, BLOCK_IP requires approval
- **Bugs**: VARYS anomaly flush, /varys/alerts includes all alerts, Wazuh no-recursion
- **Correctness**: daemon config reload propagates, schedule interval validation, CloudSync fail-fast

### 4. CLAUDE.md Updated
Full rewrite with current architecture, Python patterns, and architectural context.

---

## Current State

### Branch Status
- Branch `claude/daemon-health-check-api-UeglO` is ahead of `main`
- PR #10 was opened and closed (merge state was `dirty` — needs rebase with main)
- All changes are pushed to remote
- 913 tests passing, 0 failures

### What's Merged vs Unmerged
Everything on this branch is **unmerged** into main. The branch contains:
- VARYS cybersecurity module (18 files)
- Daemon mode with health API
- Cloudflare Workers AI integration
- Archivist v2 (7 new subsystems)
- Docker/MCP configuration
- Open WebUI integration
- 13 PR review fixes

---

## Open PR Review Comments (Still Unresolved)

These were noted but not fixed (lower priority or need design discussion):

### Web App (`guardian_one/web/app.py`)
1. **OpenAI endpoints have no auth** (line 1016) — `/v1/chat/completions` exposed without API key.
   Recommendation: add Bearer token auth or restrict to localhost.
2. **Mutates private AIEngine state** (line 1078-1079) — `_total_requests` / `_total_tokens` accessed
   directly. Should add a public `record_usage()` method to AIEngine.
3. **Backend selection uses private fields** (line 1055-1061) — `_ollama`, `_anthropic`, `_cloudflare`.
   Should add a public `get_backend(model)` method to AIEngine.
4. **max_tokens defaults to 4096** (line 1033) — exceeds AIConfig default of 2048.
   Should clamp to engine config.
5. **Model ID mismatch** (line 1127) — response returns `llama3` but `/v1/models` advertises `ollama/llama3`.

### AI Engine (`guardian_one/core/ai_engine.py`)
6. **CloudflareBackend ignores max_tokens/temperature** (line 306) — parameters accepted but not sent
   in the request payload. Should include them.

### Password Sync
7. **Sync methods don't populate password_strength** — after sync, all items show as "unassessed"
   since neither 1Password nor Bitwarden CLI exposes strength scores directly.
   May need Watchtower/Bitwarden Reports integration.

---

## What's Next (Suggested Priorities)

### High Priority
1. **Rebase branch onto main** and open a clean PR for merge
2. **Add auth to OpenAI-compatible endpoints** — Bearer token or localhost-only
3. **Add public AIEngine methods** — `get_backend(model)`, `record_usage(requests, tokens)`
4. **Wire Archivist into Guardian.run()** — so `record_interaction()` gets called by all agents

### Medium Priority
5. **Build the local AI chat loop** — connect Open WebUI to KnowledgeExporter output
6. **Implement filesystem watcher** — real-time file monitoring using watchdog or inotify
7. **Password strength assessment** — integrate Watchtower (1Password) / Reports (Bitwarden)
8. **CloudSync Cloudflare R2 integration** — requires R2 bucket creation + boto3

### Lower Priority
9. **Wazuh deployment** — uncomment in docker-compose.yml when ready for live SIEM
10. **n8n workflow automation** — connect Guardian One agents to n8n for external triggers
11. **Ring camera integration** — live feed monitoring via ring_monitor.py

---

## Key Files to Read First

| File | Why |
|------|-----|
| `CLAUDE.md` | Full architecture context, design principles, patterns |
| `guardian_one/agents/archivist.py` | Central agent — telemetry, tech detection, cloud sync |
| `guardian_one/varys/engine.py` | VARYS monitoring loop |
| `guardian_one/core/daemon.py` | Daemon mode + health API |
| `guardian_one/core/ai_engine.py` | Multi-provider AI (Ollama/Anthropic/Cloudflare) |
| `guardian_one/web/app.py` | DevPanel + OpenAI-compatible API |
| `config/guardian_config.yaml` | Agent configs, schedules, allowed_resources |

---

## Git Quick Reference

```bash
# Current branch
git checkout claude/daemon-health-check-api-UeglO

# Run tests
pytest tests/ -x -q --tb=short

# Full test count should be 913+
pytest tests/ -q 2>&1 | tail -3
```

---

## Known Gotchas

1. **Signal handling in tests** — always use `if threading.current_thread() is threading.main_thread()`
   before calling `signal.signal()`. Tests run in non-main threads.
2. **openpyxl** — must be installed for CFO dashboard tests (`pip install openpyxl`)
3. **Runtime data files** — `data/` directory contains generated state files. All gitignored.
   Don't commit them.
4. **Notion sync is write-only** — NEVER add read methods. This is a security design decision.
5. **Vault uses Fernet** (not raw AES-256-GCM) — functionally equivalent, PBKDF2 with 480K iterations.
