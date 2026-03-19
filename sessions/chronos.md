# Session Handoff: Chronos (Schedule & Calendar Management)

> Last updated: 2026-03-19
> Branch: `claude/guardian-one-system-4uvJv`

---

## What This Session Covers

You are working on **Chronos** — Guardian One's time management agent. It handles
Google Calendar sync, schedule tracking, sleep analysis, routines, workflows,
and coordination with other agents (bill reminders, meal timing, device events).

---

## Files You Own

| File | Lines | Purpose |
|------|-------|---------|
| `guardian_one/agents/chronos.py` | 424 | Core agent — events, sleep, routines, workflows |
| `guardian_one/integrations/calendar_sync.py` | 730 | Google Calendar OAuth2, pull/push, bill sync |
| `tests/test_calendar_sync.py` | 822 | 80+ tests covering all calendar operations |

---

## Data Structures

```python
@dataclass
class CalendarEvent:
    title: str
    start: datetime
    end: datetime
    location: str = ""
    category: str = "general"         # work, personal, medical, travel, routine
    source: str = "manual"            # google, epic, manual
    reminders_minutes: list[int] = [30, 10]
    metadata: dict[str, Any] = {}

@dataclass
class SleepRecord:
    date: str
    bedtime: str
    waketime: str
    duration_hours: float
    quality_score: float = 0.0        # 0-1 scale (smartwatch)

@dataclass
class Routine:
    name: str
    time_of_day: str                  # "morning", "evening", "midday"
    duration_minutes: int
    days: list[str] = ["Mon"-"Sun"]
    steps: list[str] = []

@dataclass
class CalendarEntry:                  # Google Calendar representation
    title: str
    start: datetime
    end: datetime
    location: str = ""
    source: str = ""
    event_id: str = ""
    calendar_id: str = "primary"
    description: str = ""
    raw: dict | None = None
```

---

## Method Reference

### Chronos Agent
```python
# Calendar
chronos.add_event(event: CalendarEvent) -> None
chronos.upcoming_events(hours=24) -> list[CalendarEvent]
chronos.check_conflicts() -> list[tuple[CalendarEvent, CalendarEvent]]
chronos.today_schedule() -> list[dict]        # Falls back to internal if no Google
chronos.week_schedule() -> list[dict]

# Google Calendar Sync
chronos.sync_google_calendar(days_ahead=14) -> dict  # synced, events_pulled, new_added, conflicts
chronos.sync_bills_to_calendar(bills: list[dict]) -> dict  # synced, skipped
chronos.calendar_status() -> dict

# Sleep
chronos.record_sleep(record: SleepRecord) -> None
chronos.sleep_analysis() -> dict              # avg_duration, avg_quality, recommendation

# Workflows & Routines
chronos.index_workflow(name, steps) -> None
chronos.get_workflow(name) -> list[str] | None
chronos.list_workflows() -> list[str]

# Epic (STUBBED)
chronos.prechart_checklist() -> list[str]     # Static 6-step checklist
```

### CalendarSync Engine
```python
sync = CalendarSync(provider, timezone_name="America/Chicago")
sync.connect() -> bool
sync.pull_events(days_ahead=14, days_behind=1) -> list[CalendarEntry]
sync.push_bill_to_calendar(bill_name, amount, due_date, auto_pay) -> str  # event_id
sync.sync_bills_to_calendar(bills: list[dict]) -> dict  # synced, skipped
sync.find_conflicts(events) -> list[tuple]
sync.today_schedule() -> list[CalendarEntry]
sync.week_schedule() -> list[CalendarEntry]
sync.status() -> dict
```

### GoogleCalendarProvider (OAuth2)
```python
provider = GoogleCalendarProvider(credentials_path=None, token_path=None)
provider.authenticate() -> bool
provider.fetch_events(start, end, calendar_id="primary") -> list[CalendarEntry]
provider.create_event(entry: CalendarEntry) -> str          # event_id
provider.update_event(entry: CalendarEntry) -> bool
provider.delete_event(event_id, calendar_id="primary") -> bool
provider.start_oauth_flow() -> str                          # auth URL
provider.complete_oauth_flow(open_browser=True) -> bool     # local server on port 8235
provider.status() -> dict
```

---

## Default Routines (Pre-loaded)

| Routine | Time | Duration | Days |
|---------|------|----------|------|
| Morning Skincare | morning | 15 min | Daily |
| Evening Skincare | evening | 20 min | Daily |
| Home Care | midday | 30 min | Sat-Sun |

---

## What's Working vs Stubbed

| Feature | Status | Notes |
|---------|--------|-------|
| Google Calendar OAuth2 | Working | Cached tokens, interactive flow, env var fallback |
| Event pull (14 days) | Working | Deduplicates by (title, start_time) |
| Event create/update/delete | Working | Full CRUD via Calendar API v3 |
| Bill sync to calendar | Working | Pushes unpaid CFO bills, avoids duplicates |
| Today/week schedule | Working | Offline fallback to internal events |
| Conflict detection | Working | Overlapping time ranges |
| Sleep tracking | Working | 7-day rolling average + heuristic |
| Workflow indexing | Working | Key-value store |
| Routines | Working | 3 pre-loaded, but no notifications |
| **Epic FHIR** | **Stubbed** | Auth not implemented, static checklist only |
| **Wake-up alerts** | **Not built** | Config exists (`wake_alert_minutes_before: 30`) |
| **Routine notifications** | **Not built** | Stored but never triggered |

---

## Development Tracks

### Track 1: Epic FHIR Integration (Medical Scheduling)
- `EpicScheduleProvider` exists but returns False on authenticate()
- Needs SMART on FHIR implementation
- Pull patient scheduling, pre-charting data
- Dynamic checklist based on appointment type

### Track 2: Wake-Up Alerts
- Config has `wake_alert_minutes_before: 30`
- No code reads this config value
- Should trigger notification 30 min before calculated wake time
- Coordinate with sleep analysis data

### Track 3: Routine Notifications
- 3 routines stored but never surfaced
- Need notification integration (email, SMS, push)
- Trigger at `time_of_day` with duration estimates

### Track 4: Multi-Calendar Support
- Only "primary" calendar used
- Add work/personal calendar support
- Config: `allowed_calendars: ["primary", "work", "personal"]`

### Track 5: Workflow Execution Tracking
- Currently stores steps as list[str]
- Add execution tracking (which steps done, time taken)
- Sync multi-step workflows to Google Tasks

### Track 6: Cross-Agent Coordination
- Chronos → DeviceAgent: Already fires wake/sleep/leave/arrive events
- CFO → Chronos: Bill sync already working
- DoorDash → Chronos: Meal timing coordination (configured, needs wiring)
- WebArchitect → Chronos: Maintenance window scheduling

---

## CLI Commands

```bash
python main.py --calendar             # Today's schedule
python main.py --calendar-week        # This week's schedule
python main.py --calendar-sync        # Sync Google Calendar + push bills
python main.py --calendar-auth        # Run Google Calendar OAuth flow
```

---

## Config (guardian_config.yaml)

```yaml
agents:
  chronos:
    enabled: true
    schedule_interval_minutes: 15
    allowed_resources: [calendar, sleep_data, routines, workflows]
    custom:
      wake_alert_minutes_before: 30
      prechart_reminder: true
```

---

## Test Coverage

**80+ tests** in `test_calendar_sync.py`:
- CalendarEntry model validation
- GoogleCalendarProvider credentials (10 tests)
- Token load/save/refresh (6 tests)
- API fetch/create/update/delete (13 tests)
- CalendarSync pull/push/conflicts (17 tests)
- Chronos integration sync + dedup (9 tests)
- EpicScheduleProvider stub behavior (8 tests)
- Utility functions (3 tests)

**Not tested:** Real HTTP calls, network timeouts, multi-calendar.
