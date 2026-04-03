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

---

## Industry Practices Review

### Test Pattern Quality

#### What's Done Well

| Practice | Status | Evidence |
|----------|--------|----------|
| **AAA Pattern** (Arrange-Act-Assert) | Strong | Consistent across all 25 files; clear separation of setup, action, verification |
| **Test Isolation** | Excellent | No shared state; each test creates fresh instances; `tempfile.mkdtemp()` for disk isolation |
| **Mock Strategy** | Excellent | External deps (APIs, SMTP, Ollama, Anthropic) properly isolated via `unittest.mock.patch`; zero flaky network calls |
| **Security Testing** | Excellent | Threat model validation, access control boundaries, crypto roundtrips, read-only enforcement (Plaid), TLS enforcement, rate limiting |
| **Test Naming** | Strong | `test_[component]_[scenario]` convention; descriptive and scannable |
| **Error Resilience** | Strong | `test_manager_survives_channel_exception` pattern; gateway rejects unregistered services; vault wrong-passphrase handling |
| **Persistence Roundtrips** | Good | CFO data reload, audit disk persistence, vault encrypt/decrypt, Plaid token store |
| **Idempotency Testing** | Good | `test_cfo_csv_sync_deduplicates` — syncs same CSV twice, verifies no duplication |

#### What Needs Improvement

| Practice | Status | Gap | Industry Standard |
|----------|--------|-----|-------------------|
| **`pytest.fixture` usage** | Weak | Helper functions (`_make_audit()`, `_make_cfo()`) used instead of fixtures | Fixtures provide scoping (session/module/function), automatic teardown, dependency injection, and IDE support. Convert helpers to `@pytest.fixture` in `conftest.py` |
| **`@pytest.mark.parametrize`** | Minimal | Nearly zero parametrized tests across 850+ cases | Data-driven tests reduce duplication. Email commands (10 separate functions) should be 1 parametrized test. Urgency levels, filter operations, category mappings are all candidates |
| **Negative/Error Path Coverage** | Inconsistent | Security tests strong; agent tests lack invalid-input and failure-mode tests | Industry ratio: ~30% negative tests. Missing: invalid dates, malformed CSV, duplicate IDs, agent crash during run, corrupted encrypted data |
| **Boundary/Edge Case Testing** | Fair | Some boundary tests exist (Chronos conflicts, CFO down-payment gap) but not systematic | Test at boundaries: empty collections, max-size inputs, off-by-one timestamps, midnight/DST transitions, zero-length strings |
| **Fragile Assertions** | Minor | String matching like `"healthy" in analysis["recommendation"].lower()` | Prefer structured assertions: check enum values, dict keys, or use `pytest.approx()` for floats |
| **Hardcoded Paths** | Minor | `parse_rocket_money_csv("/tmp/does_not_exist.csv")` in `test_financial_sync.py` | Use `tempfile.TemporaryDirectory()` or `tmp_path` fixture for portability |
| **`os.environ` patching** | Minor | `patch.dict("os.environ", {}, clear=True)` removes ALL env vars | Patch only the specific vars needed; `clear=True` is brittle if test runner sets vars |

### Test Infrastructure Gaps

#### Missing: `conftest.py` — HIGH Priority

No shared fixture file exists. Industry standard is a `tests/conftest.py` providing:

```python
# Reusable fixtures with proper scoping
@pytest.fixture
def audit_log(tmp_path):
    return AuditLog(log_dir=tmp_path / "audit")

@pytest.fixture
def guardian_config():
    return GuardianConfig(owner="test", ...)

@pytest.fixture
def vault(tmp_path):
    return Vault(vault_path=tmp_path / "vault", passphrase="test")

# Session-scoped for expensive setup
@pytest.fixture(scope="session")
def sample_cfo_data():
    ...
```

**Impact:** Eliminates duplicated `_make_audit()` helpers across 10+ files.

#### Missing: Coverage Measurement — HIGH Priority

No `.coveragerc`, no `pytest-cov` in dependencies. Cannot measure or enforce coverage thresholds.

**Recommended `.coveragerc`:**
```ini
[run]
source = guardian_one
branch = true
omit =
    */templates/*
    */__init__.py

[report]
fail_under = 75
show_missing = true
exclude_lines =
    pragma: no cover
    if __name__ == .__main__
    raise NotImplementedError
```

**Recommended addition to `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
addopts = "--cov=guardian_one --cov-report=term-missing --cov-fail-under=75"
```

#### Missing: CI/CD Pipeline — HIGH Priority

No `.github/workflows/`, no `tox.ini`, no `Makefile`. Tests only run manually.

**Recommended `.github/workflows/tests.yml`:**
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --cov=guardian_one --cov-report=xml
      - uses: codecov/codecov-action@v4  # optional
```

#### Missing: Test Tooling — MEDIUM Priority

| Tool | Purpose | Status |
|------|---------|--------|
| `pytest-cov` | Coverage measurement and thresholds | **Missing** |
| `pytest-mock` | Cleaner `mocker` fixture instead of `unittest.mock` | **Missing** |
| `pytest-xdist` | Parallel test execution (`-n auto`) | **Missing** — 850+ tests would benefit |
| `pytest-timeout` | Kill hanging tests (integration tests, thread tests) | **Missing** |
| `pytest-randomly` | Detect hidden test-order dependencies | **Missing** |
| `hypothesis` | Property-based / fuzz testing for parsers and validators | **Missing** |

#### Missing: Test Data Organization — MEDIUM Priority

No `tests/fixtures/` or `tests/data/` directory. Test data is either inline or in the top-level `data/` folder.

**Recommended structure:**
```
tests/
├── conftest.py              # Shared fixtures
├── fixtures/
│   ├── sample_config.yaml   # Valid config for config.py tests
│   ├── sample_csv/          # Rocket Money CSV samples
│   └── sample_responses/    # Mock API response payloads
├── data/                    # Larger test datasets
└── ...
```

#### Missing: Makefile — MEDIUM Priority

```makefile
.PHONY: test coverage lint typecheck

test:
	pytest tests/ -v

coverage:
	pytest tests/ --cov=guardian_one --cov-report=html
	open htmlcov/index.html

lint:
	ruff check guardian_one/ tests/
	black --check guardian_one/ tests/

typecheck:
	mypy guardian_one/
```

### Testing Pyramid Assessment

Industry standard testing pyramid recommends a ratio of roughly **70% unit / 20% integration / 10% E2E**.

| Layer | Current State | Target |
|-------|--------------|--------|
| **Unit Tests** | ~830 tests (98%) — Strong | Maintain; fill gaps in untested modules |
| **Integration Tests** | ~20 tests (2%) — Weak | Add cross-agent flows (CFO+Gmail, Chronos+CFO, Guardian orchestration) |
| **E2E / Smoke Tests** | 0 tests (0%) — Missing | Add CLI smoke tests (`main.py` subcommands), full boot-to-summary cycle |

The suite is **bottom-heavy** — excellent unit coverage but almost no integration or end-to-end validation.

### Property-Based Testing Candidates

The `hypothesis` library would add significant value for these modules:

| Module | Property to Test |
|--------|-----------------|
| `utils/encryption.py` | `decrypt(encrypt(data)) == data` for arbitrary bytes |
| `core/config.py` | `load_config(write_config(cfg)) == cfg` roundtrip |
| `integrations/financial_sync.py` | `map_category()` never raises for arbitrary strings |
| `integrations/notion_sync.py` | `classify_content()` blocks all PHI/PII patterns (fuzz SSN, CC, email variants) |
| `homelink/email_commands.py` | Parser never crashes on arbitrary email body strings |
| `core/mediator.py` | No proposal is silently dropped (all proposals appear in resolution or conflict) |

### Recommended Test Markers

```python
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests that take >1s (deselect with '-m not slow')",
    "integration: cross-agent or multi-component tests",
    "security: security-focused test cases",
    "smoke: minimal sanity checks for CI fast-path",
]
```

### Summary: Priority Action Items

| # | Action | Priority | Effort | Impact |
|---|--------|----------|--------|--------|
| 1 | Create `tests/conftest.py` with shared fixtures | HIGH | Low | Eliminates duplication, enables fixture scoping |
| 2 | Add `pytest-cov` + `.coveragerc` with 75% threshold | HIGH | Low | Measurable coverage, CI gate |
| 3 | Add GitHub Actions CI workflow | HIGH | Low | Automated test runs on every push/PR |
| 4 | Write `test_config.py` and `test_base_agent.py` | HIGH | Medium | Covers 2 foundational modules |
| 5 | Add `@pytest.mark.parametrize` to 5 key test files | HIGH | Medium | Reduce duplication, increase data coverage |
| 6 | Write integration tests for 3 cross-agent flows | MEDIUM | Medium | Validate system behavior, not just components |
| 7 | Add `pytest-timeout`, `pytest-randomly` | MEDIUM | Low | Catch hanging tests and order dependencies |
| 8 | Write `test_drivers.py` and `test_lan_security.py` | MEDIUM | Medium | Cover hardware control and network security |
| 9 | Add `hypothesis` property-based tests for parsers | MEDIUM | Medium | Catch edge cases humans miss |
| 10 | Add Makefile with `test`, `coverage`, `lint` targets | MEDIUM | Low | Standardize developer workflow |
| 11 | Add CLI smoke tests for `main.py` subcommands | LOW | Medium | E2E confidence for top-level entry point |
| 12 | Add `pytest-xdist` for parallel execution | LOW | Low | Faster CI runs as test count grows |
