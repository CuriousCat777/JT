# Test Coverage Analysis — Guardian One

**Date:** 2026-04-03
**Current State:** 25 test files, ~850+ test cases

## Coverage Summary

| Source Module | Test File | Status | Tests |
|---------------|-----------|--------|-------|
| `agents/chronos.py` | `test_agents.py`, `test_calendar_sync.py` | Covered | ~23 |
| `agents/archivist.py` | `test_agents.py` | **Thin** | 5 |
| `agents/cfo.py` | `test_agents.py`, `test_financial_sync.py` | Covered | ~111 |
| `agents/doordash.py` | `test_doordash.py` | Covered | 39 |
| `agents/gmail_agent.py` | `test_gmail.py` | Covered | 65 |
| `agents/web_architect.py` | `test_web_architect.py` | Covered | 73 |
| `agents/website_manager.py` | `test_website_manager.py` | Covered | 52 |
| `agents/device_agent.py` | `test_devices.py` | Covered | 153 |
| `agents/cfo_dashboard.py` | — | **NO TESTS** | 0 |
| `core/guardian.py` | `test_guardian.py` | Covered | 11 |
| `core/ai_engine.py` | `test_ai_engine.py` | Covered | 45 |
| `core/audit.py` | `test_audit.py` | **Thin** | 6 |
| `core/mediator.py` | `test_mediator.py` | Covered | 31 |
| `core/scheduler.py` | `test_scheduler.py` | Covered | 27 |
| `core/sandbox.py` | `test_sandbox_eval.py` | Covered | 25 |
| `core/evaluator.py` | `test_sandbox_eval.py` | Covered | 25 |
| `core/security.py` | `test_security.py` | Covered | 11 |
| `core/cfo_router.py` | `test_cfo_router.py` | Covered | 39 |
| `core/security_remediation.py` | `test_security_remediation.py` | Covered | 57 |
| `core/config.py` | — | **NO TESTS** | 0 |
| `core/base_agent.py` | — | **NO TESTS** | 0 |
| `homelink/vault.py` | `test_homelink.py` | Covered | 7 |
| `homelink/gateway.py` | `test_homelink.py` | Covered | 9 |
| `homelink/registry.py` | `test_homelink.py` | Covered | 12 |
| `homelink/monitor.py` | `test_homelink.py` | Covered | 5 |
| `homelink/email_commands.py` | `test_homelink.py` | Covered | 23 |
| `homelink/devices.py` | `test_devices.py` | Covered | 153 |
| `homelink/automations.py` | `test_devices.py` | **Partial** | ~14 |
| `homelink/drivers.py` | — | **NO TESTS** | 0 |
| `homelink/lan_security.py` | — | **NO TESTS** | 0 |
| `integrations/calendar_sync.py` | `test_calendar_sync.py` | Covered | 97 |
| `integrations/financial_sync.py` | `test_financial_sync.py` | Covered | 95 |
| `integrations/notion_sync.py` | `test_notion_sync.py` | Covered | 77 |
| `integrations/notion_website_sync.py` | `test_notion_website_sync.py` | Covered | 11 |
| `integrations/notion_remediation_sync.py` | `test_notion_remediation_sync.py` | Covered | 11 |
| `integrations/ollama_sync.py` | `test_ollama_sync.py` | Covered | 44 |
| `integrations/gmail_sync.py` | `test_gmail.py` | **Partial** | — |
| `integrations/n8n_sync.py` | `test_web_architect.py` | **Partial** | — |
| `integrations/doordash_sync.py` | — | **NO TESTS** | 0 |
| `integrations/ring_monitor.py` | — | **NO TESTS** | 0 |
| `integrations/plaid_connect.py` | — | **NO TESTS** | 0 |
| `integrations/privacy_tools.py` | — | **NO TESTS** | 0 |
| `utils/encryption.py` | `test_encryption.py` | Covered | 18 |
| `utils/notifications.py` | `test_notifications.py` | Covered | 94 |
| `web/app.py` | `test_devpanel.py` | **Partial** | 24 |
| `main.py` | — | **NO TESTS** | 0 |

## Modules with NO Tests (Priority Order)

### 1. `core/config.py` — HIGH Priority
Every agent depends on `load_config()`. A regression here breaks everything.

**Recommended tests:**
- Load valid YAML config and verify defaults
- Handle missing config file (falls back to defaults)
- Environment variable overrides (`GUARDIAN_DATA_DIR`, `GUARDIAN_LOG_DIR`)
- Nested agent config parsing with custom properties
- Invalid YAML handling

### 2. `core/base_agent.py` — HIGH Priority
Foundation for all 7 agents — lifecycle, AI injection, audit logging.

**Recommended tests:**
- Full lifecycle: init → initialize → run → report → shutdown
- Status transitions: IDLE → RUNNING → ERROR → DISABLED
- `think()` returns deterministic fallback when AI unavailable
- `think_quick()` extracts content correctly
- `set_ai_engine()` injection and removal
- `log()` helper delegates to audit correctly
- `shutdown()` records audit entry

### 3. `homelink/drivers.py` — HIGH Priority
Controls real smart home hardware; incorrect behavior = lights/locks misbehaving. 6 drivers + `DriverFactory` with 25+ methods.

**Recommended tests:**
- Each driver's `turn_on/off()` success/failure result format
- `DriverFactory.for_device()` routing by device type
- Missing library detection (graceful `_fail()` response)
- Hue brightness scaling (0-100 → 0-254)
- Govee LAN UDP packet construction
- Govee cloud API auth header injection
- LG WebOS async-to-sync conversion

### 4. `homelink/lan_security.py` — MEDIUM Priority
VLAN violations, default credentials, DNS blocklist auditing.

**Recommended tests:**
- VLAN violation detection logic
- Cloud-dependent device flagging
- Default password device detection
- Risk scoring (1-5 scale)
- DNS blocklist domain/wildcard aggregation
- `full_audit()` report structure
- Pi-hole/NextDNS detection

### 5. `integrations/doordash_sync.py` — MEDIUM Priority
JWT generation, token refresh, delivery CRUD.

**Recommended tests:**
- JWT creation (HS256, `DD-JWT-V1` header, 5-min expiry)
- Token auto-refresh (after 240s)
- Delivery create/get/cancel API calls
- HTTP error handling (4xx/5xx)
- Missing credentials graceful degradation

### 6. `integrations/ring_monitor.py` — MEDIUM Priority
Background polling thread, event deduplication, vault token retrieval.

**Recommended tests:**
- Event deduplication via `_seen_event_ids`
- Priority event detection and alerting
- Background polling thread start/stop
- Vault token retrieval failure handling
- `manteca_events()` location filtering

### 7. `integrations/plaid_connect.py` — MEDIUM Priority
Token exchange endpoint handles bank credentials.

**Recommended tests:**
- Server startup on localhost (127.0.0.1 only)
- HTML page rendering with link_token substitution
- Token exchange endpoint (parse request, call plaid.exchange_public_token)
- Missing credentials error handling

### 8. `integrations/privacy_tools.py` — LOW Priority
CLI wrapper + API client; external dependency heavy.

**Recommended tests:**
- Credential detection (env vars, CLI availability)
- VPNStatus field extraction
- Country name sanitization (block injection)
- CLI missing graceful fallback

### 9. `agents/cfo_dashboard.py` — LOW Priority
Excel workbook generation.

**Recommended tests:**
- Dashboard generates valid Excel with 4 sheets
- Handles empty CFO data gracefully
- Column headers match expected format

### 10. `main.py` — LOW Priority
CLI entry point, 25+ subcommands.

**Recommended tests:**
- Argument parsing for each subcommand
- Agent instantiation with correct config/audit injection
- Error handling for missing agents

## Modules with THIN/PARTIAL Coverage

### `core/audit.py` (6 tests → should be ~15)
- Concurrent write safety
- Log rotation when file exceeds `max_file_bytes`
- `search()` full-text query
- `export()` to CSV and JSON formats
- Persistence across restarts

### `agents/archivist.py` (5 tests → should be ~15)
- File encryption roundtrip
- Privacy audit detail checks
- Master profile structure validation
- Retention policy enforcement (`audit_retention_policy`)
- Data source sync

### `homelink/automations.py` (partial in test_devices.py)
- `_rule_matches_context()` edge cases
- PAUSED status behavior
- Room-scoped rule filtering
- `delay_seconds` action logic
- Duplicate event ID prevention

### `web/app.py` (24 tests, but gaps)
- Audit query filtering params (agent, severity, limit)
- Invalid agent name → 404
- Run-all error handling when an agent fails
- Thread-safe Guardian singleton

### `integrations/gmail_sync.py` (partial via test_gmail.py)
- `get_attachment()` and `search_messages()` provider methods
- OAuth2 token refresh flow
- Base64 decoding with padding correction
- Multipart message parsing edge cases

### `integrations/n8n_sync.py` (partial via test_web_architect.py)
- `N8nAPIProvider` CRUD operations (list, execute, get workflow)
- API header injection
- HTTP error handling
- Workflow node structure preservation

## Missing Test Categories

### Cross-Agent Integration Tests
The suite is strong on unit tests but lacks end-to-end flows:
- Mediator resolving conflicts between real agent instances
- CFO + Gmail: Rocket Money CSV auto-download → financial sync
- Chronos + CFO: bill reminders appearing on calendar
- Guardian orchestration: full boot → run all → summary
- Notification routing: agent alert → AlertRouter → correct channel

### Error Resilience / Edge Cases
- Network timeout handling across all providers
- Vault passphrase change / corruption recovery
- Gateway circuit breaker state transitions (CLOSED → OPEN → HALF_OPEN)
- Agent crash recovery (status ERROR → re-run)

### Security-Focused Tests
- Content classification gate (PHI/PII patterns) under adversarial input
- Access control boundary testing (agent accessing another agent's resources)
- Secret store behavior with corrupted encrypted data
- Vault credential rotation during active use

## Quick Wins (Most Coverage for Least Effort)

1. **`test_config.py`** — ~5 tests, `load_config()` is a pure function
2. **`test_base_agent.py`** — ~10 tests, create a concrete stub of the ABC
3. **Expand `test_audit.py`** — add 5 tests for rotation, search, export
4. **`test_lan_security.py`** — pure logic, no external deps, easy to mock
5. **`test_drivers.py`** — mock all hardware libs, test result format consistency
