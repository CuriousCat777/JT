# Guardian One: 10 Steps to Go Live

Roadmap for taking Guardian One from a working prototype to a production system
that runs 24/7 and reliably manages Jeremy's life operations.

---

## 1. Persistent Background Service (Daemon Mode)

**Status:** COMPLETE
**Why:** Right now Guardian One only runs when you manually invoke `python main.py`.
For a live system, it needs to run continuously as a background service that
survives reboots, crashes, and SSH disconnects.

**Tasks:**
- [x] Create a systemd service unit (`guardian-one.service`) for Linux deployment
- [x] Add auto-restart on crash with backoff (`Restart=on-failure`)
- [x] Add a `--daemon` flag to `main.py` that runs the scheduler in headless mode
      (no interactive prompt, just scheduled agent cycles + health endpoint)
- [x] Write a startup script that loads `.env`, checks dependencies, and launches
- [x] Add graceful shutdown with SIGTERM handling and state persistence

---

## 2. Health Check & Status API

**Status:** COMPLETE (core endpoints live, notification wiring pending)
**Why:** A live system needs a way to check "is Guardian One running and healthy?"
without SSH-ing in and reading logs. Also enables monitoring/alerting if it goes down.

**Tasks:**
- [x] Add a lightweight HTTP health endpoint (`/health` on a local port)
      that returns system status, agent states, last run times, uptime
- [x] Add a `/status` endpoint with detailed agent reports (JSON)
- [x] Add a `/metrics` endpoint for key numbers (net worth, alert count,
      agents healthy, last sync time)
- [ ] Wire health checks into the notification system — if Guardian One itself
      is unhealthy, send an alert

---

## 3. Real Credential & Secret Management

**Status:** MOSTLY COMPLETE (passphrase enforced, random salts, rotation tracking)
**Why:** Going live means real API keys, bank tokens, and OAuth credentials.
The default dev passphrase needs to go. Secrets must be locked down.

**Tasks:**
- [x] Remove the hardcoded default passphrase (`guardian-one-default-dev-passphrase`)
- [x] Require `GUARDIAN_MASTER_PASSPHRASE` to be set at startup (fail fast if missing)
- [ ] Add credential validation on boot — verify Plaid tokens, Google OAuth,
      SMTP credentials are present and working before marking agents "ready"
- [x] Add automatic credential rotation reminders (Vault already tracks rotation dates)
- [ ] Document the full list of required credentials per agent in a setup guide

---

## 4. Persistent Data Layer (SQLite)

**Status:** Not started (currently JSON files + in-memory)
**Why:** Financial data, audit logs, transaction history, and agent state
need to survive restarts and be queryable. JSON files don't scale.

**Tasks:**
- [ ] Add SQLite database for transactions, accounts, balances, audit log
- [ ] Migrate CFO ledger from JSON → SQLite with proper schema
- [ ] Store audit log entries in SQLite (keep file log as backup)
- [ ] Add agent state persistence — last run, last result, error counts
- [ ] Add database migrations strategy for future schema changes
- [ ] Add backup/export command (`--export` to dump DB to JSON for portability)

---

## 5. Error Recovery & Resilience

**Status:** Basic (try/except in run loops)
**Why:** A live system will hit network failures, API rate limits, expired tokens,
and corrupted state. It needs to handle all of these gracefully without crashing.

**Tasks:**
- [ ] Add retry logic with exponential backoff for all external API calls
      (Plaid, Google Calendar, Gmail, Empower)
- [ ] Add circuit breaker pattern to Gateway (partially exists) — verify it
      actually prevents cascading failures
- [ ] Add agent-level error budgets: if an agent fails N times in a row,
      auto-pause it and notify Jeremy
- [ ] Add state recovery on startup — detect incomplete sync cycles and resume
- [ ] Add watchdog: if scheduler thread dies, restart it automatically

---

## 6. Structured Logging & Observability

**Status:** Partial (AuditLog exists, but no structured operational logging)
**Why:** When something goes wrong at 3 AM, you need searchable, structured logs
to diagnose what happened. The audit log tracks actions but not operational details.

**Tasks:**
- [ ] Add Python `logging` with structured JSON output (separate from audit log)
- [ ] Log levels: DEBUG for agent internals, INFO for lifecycle, WARNING for
      retries, ERROR for failures, CRITICAL for system-level issues
- [ ] Add log rotation (daily, keep 30 days)
- [ ] Add correlation IDs per sync cycle so you can trace a full cycle through logs
- [ ] Add a `--logs` CLI command to tail/search recent log entries

---

## 7. Automated Test Suite & CI

**Status:** MOSTLY COMPLETE (733 tests passing, CI pipeline active)
**Why:** Before going live (and before every update), you need confidence that
changes don't break things. Tests need to run automatically.

**Tasks:**
- [x] Ensure all test files pass cleanly (`pytest tests/` — 733 passing)
- [ ] Add integration test that boots GuardianOne, registers all agents,
      runs a full cycle, and verifies reports
- [x] Add GitHub Actions workflow (`.github/workflows/test.yml`)
      that runs tests on every push
- [ ] Add test coverage tracking (target: 80%+)
- [ ] Add a pre-commit hook or CI check for linting (ruff/flake8)

---

## 8. Deployment & Environment Setup

**Status:** Not started
**Why:** Need a repeatable way to deploy Guardian One on a server (VPS, Raspberry Pi,
or cloud VM) with all dependencies, configs, and credentials in place.

**Tasks:**
- [ ] Create `Dockerfile` for containerized deployment
- [ ] Create `docker-compose.yml` with volume mounts for data, logs, config
- [ ] Write deployment guide: server requirements, Python version, env vars,
      credential setup, first-run checklist
- [ ] Add `scripts/setup.sh` — install dependencies, create directories,
      validate config, run initial tests
- [ ] Add `scripts/backup.sh` — backup data dir, SQLite DB, vault, configs

---

## 9. Live Notification Pipeline

**Status:** Partial (email/SMS channels exist, routing exists)
**Why:** Notifications are the primary way Guardian One communicates with Jeremy
in production. They need to be reliable, not spammy, and actionable.

**Tasks:**
- [ ] End-to-end test the full notification flow: agent detects issue → router
      evaluates urgency → channel delivers → delivery confirmed
- [ ] Add delivery confirmation/receipts (did the email actually send?)
- [ ] Add notification deduplication — don't send the same alert twice in 24h
- [ ] Add daily digest mode: batch low-urgency notifications into a single
      morning summary instead of individual alerts
- [ ] Add push notification channel (Pushover, ntfy, or Telegram bot)
      as a faster alternative to email for urgent alerts
- [ ] Verify quiet hours work correctly across timezone/DST changes

---

## 10. Live Cutover Checklist & Dry Run

**Status:** Not started
**Why:** Before flipping the switch, run Guardian One in "shadow mode" alongside
manual processes to verify it produces correct results.

**Tasks:**
- [ ] Run Guardian One in dry-run mode for 7 days: all agents execute, all
      notifications fire, but no external side effects (read-only)
- [ ] Compare CFO financial reports against manual Empower/Rocket Money checks
- [ ] Verify calendar sync matches actual Google Calendar state
- [ ] Verify notification delivery at different times of day (quiet hours, etc.)
- [ ] Confirm audit log captures everything needed for accountability
- [ ] Document "runbook" for common operations: restart, pause agent, check logs,
      rotate credentials, recover from crash
- [ ] Set a go-live date and switch to Guardian One as primary system

---

## Priority Order

| Phase | Items | Goal | Status |
|-------|-------|------|--------|
| **Foundation** | 1, 3, 4 | Can run unattended with real credentials and persistent data | 1 done, 3 mostly done, 4 not started |
| **Reliability** | 5, 6, 7 | Won't silently fail; you'll know when something's wrong | 7 mostly done, 5-6 not started |
| **Deployment** | 2, 8, 9 | Deployable, observable, communicates proactively | 2 done, 8-9 not started |
| **Go-Live** | 10 | Validated and trusted — flip the switch | Blocked by above |
