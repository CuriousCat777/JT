# Session Handoff: Archivist (Data Sovereignty & Privacy)

> Last updated: 2026-03-19
> Branch: `claude/guardian-one-system-4uvJv`

---

## What This Session Covers

You are working on **The Archivist** — Guardian One's data sovereignty agent.
It manages file organization, retention policies, master profile autofill,
privacy tool monitoring (NordVPN, DeleteMe), and data source sync.

---

## Files You Own

| File | Lines | Purpose |
|------|-------|---------|
| `guardian_one/agents/archivist.py` | 289 | Core agent — files, privacy audit, master profile |
| `guardian_one/integrations/privacy_tools.py` | 244 | NordVPN CLI + DeleteMe API providers |
| `tests/test_agents.py` (lines 101-148) | 48 | 5 Archivist tests (shallow) |

---

## Data Structures

```python
class RetentionPolicy(Enum):
    KEEP_FOREVER = "keep_forever"        # Never delete
    KEEP_1_YEAR = "keep_1_year"          # 365 days
    KEEP_3_YEARS = "keep_3_years"        # 1095 days (default)
    KEEP_7_YEARS = "keep_7_years"        # 2555 days (tax/legal)
    DELETE_AFTER_USE = "delete_after_use" # 0 days

@dataclass
class FileRecord:
    path: str
    category: str           # medical, financial, personal, professional, legal
    tags: list[str]
    retention: RetentionPolicy = KEEP_3_YEARS
    encrypted: bool = False
    last_accessed: str = ""  # ISO timestamp
    created: str = ""        # ISO timestamp

@dataclass
class DataSource:
    name: str               # "Smartwatch", "NordVPN", "DeleteMe"
    source_type: str        # smartwatch, vpn, privacy_service, app
    data_types: list[str]   # heart_rate, steps, sleep, connection_log, etc.
    sync_enabled: bool
    last_sync: str | None
    config: dict[str, Any]

@dataclass
class PrivacyTool:
    name: str               # "NordVPN", "DeleteMe"
    tool_type: str          # vpn, data_broker_removal, password_manager, encryption
    active: bool = True
    config: dict[str, Any] = {}
    last_check: str | None = None

@dataclass
class VPNStatus:
    connected: bool
    server: str = ""
    country: str = ""
    protocol: str = ""
    ip_address: str = ""

@dataclass
class BrokerRemovalReport:
    scan_date: str
    brokers_found: int
    brokers_removed: int
    pending_removals: int
    exposures: list[dict] = []
```

---

## Method Reference

### Archivist Agent
```python
# File Management
archivist.register_file(record: FileRecord) -> None
archivist.search_files(query=None, category=None, tags=None) -> list[FileRecord]
archivist.files_due_for_deletion() -> list[FileRecord]

# Master Profile (Autofill)
archivist.set_profile_field(key: str, value: Any) -> None
archivist.get_profile() -> dict[str, Any]

# Data Sources
archivist.sync_source(name: str) -> dict    # Updates timestamp only (STUB)

# Privacy
archivist.privacy_audit() -> dict           # issues, recommendations, tools_active, tools_total

# BaseAgent
archivist.run() -> AgentReport              # Check retention + privacy, return alerts
archivist.report() -> AgentReport           # State snapshot
```

### NordVPNProvider
```python
nordvpn = NordVPNProvider()
nordvpn.has_credentials -> bool          # Token OR CLI available
nordvpn.status() -> VPNStatus            # Parses `nordvpn status` CLI output
nordvpn.connect(country=None) -> bool    # Runs `nordvpn connect [country]`
nordvpn.disconnect() -> bool             # Runs `nordvpn disconnect`
nordvpn.provider_status() -> dict        # Diagnostic info
```

### DeleteMeProvider
```python
deleteme = DeleteMeProvider(api_key=None)
deleteme.has_credentials -> bool         # API key set
deleteme.latest_report() -> BrokerRemovalReport | None   # STUB — returns None
deleteme.trigger_scan() -> bool                           # STUB — returns False
deleteme.provider_status() -> dict       # Diagnostic info
```

---

## Defaults (Pre-loaded)

**Data Sources:**
| Source | Type | Data Types |
|--------|------|-----------|
| Smartwatch | smartwatch | heart_rate, steps, sleep, stress |
| NordVPN | vpn | connection_log, bandwidth |
| DeleteMe | privacy_service | broker_removal_status, exposure_report |

**Privacy Tools:**
| Tool | Type | Config |
|------|------|--------|
| NordVPN | vpn | auto_connect: true, kill_switch: true, protocol: NordLynx |
| DeleteMe | data_broker_removal | scan_frequency: quarterly, auto_remove: true |

**Backup Schedule:**
| Category | Frequency |
|----------|-----------|
| Medical | Weekly |
| Financial | Daily |
| Personal | Weekly |
| Professional | Daily |
| Legal | Monthly |

---

## What's Working vs Stubbed

| Feature | Status | Notes |
|---------|--------|-------|
| File registration & search | Working | In-memory, filters by category/tags/query |
| Retention calculation | Working | Date math, handles timezone, all policies |
| Master profile | Working | Simple key-value store |
| Privacy audit logic | Working | Detects inactive tools, missing encryption, VPN kill switch |
| NordVPN CLI integration | Working | Requires `nordvpn` CLI installed |
| **Data source sync** | **Stub** | Updates timestamp only, no real API calls |
| **DeleteMe API** | **Stub** | Credential detection works, API not implemented |
| **NordVPN token API** | **Stub** | Token read but never used in API calls |
| **File encryption** | **Not built** | `encrypted` flag exists, no encryption logic |
| **Backup orchestration** | **Not built** | Schedule defined, no backup execution |
| **Auto-encrypt sensitive** | **Not built** | Config flag exists, not consumed |

---

## Development Tracks

### Track 1: DeleteMe API (Data Broker Removal)
- Implement `latest_report()`: `GET /api/v1/reports/latest`
- Implement `trigger_scan()`: `POST /api/v1/scans`
- Parse `BrokerRemovalReport` from response
- Env: `DELETEME_API_KEY`, `DELETEME_BASE_URL`

### Track 2: File Encryption
- Use Vault (AES-256-GCM) to encrypt files marked sensitive
- Auto-encrypt medical/financial/legal files on registration
- Config: `auto_encrypt_sensitive: true` already in YAML

### Track 3: Expand Test Coverage
- `files_due_for_deletion()` — date math, edge cases
- `sync_source()` — found/not-found paths
- `privacy_audit()` — content assertions (currently shallow)
- NordVPN provider — mock subprocess calls
- DeleteMe provider — mock API responses

### Track 4: Real Data Source Sync
- Smartwatch: Fitbit/Apple Watch/Garmin API integration
- NordVPN: Parse connection logs from `~/.nordvpn/`
- DeleteMe: Wire up API (Track 1)

### Track 5: Backup Orchestration
- `_backup_schedule` defined but unused
- Implement backup to encrypted local storage
- Coordinate with file retention policies
- Alert on missed backups

---

## Privacy Audit Logic (What It Checks)

1. Any privacy tool with `active=False` → issue
2. VPN tools without `kill_switch: true` → issue
3. Unencrypted files in `financial`, `medical`, `legal` categories → issue
4. Each issue gets a matching recommendation

---

## Config (guardian_config.yaml)

```yaml
agents:
  archivist:
    enabled: true
    schedule_interval_minutes: 60
    allowed_resources: [file_index, data_sources, privacy_tools, master_profile]
    custom:
      auto_encrypt_sensitive: true     # NOT IMPLEMENTED
      retention_check_daily: true      # NOT IMPLEMENTED
```

---

## Cross-Agent Integration

| Agent | Integration | Direction |
|-------|-------------|-----------|
| **CFO** → Archivist | Financial docs need KEEP_7_YEARS retention | CFO → Archivist |
| **Gmail** → Archivist | Downloaded CSVs registered as financial files | Gmail → Archivist |
| **DeviceAgent** → Archivist | Camera footage storage management | DeviceAgent → Archivist |
| **Guardian** → Archivist | Master profile used for autofill across agents | Archivist → All |
