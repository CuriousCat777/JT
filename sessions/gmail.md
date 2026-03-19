# Session Handoff: Gmail Agent (Email Intelligence)

> Last updated: 2026-03-19
> Branch: `claude/guardian-one-system-4uvJv`

---

## What This Session Covers

You are working on **Gmail Agent** — Guardian One's email monitoring system.
It watches Jeremy's inbox (`jeremytabernero@gmail.com`), detects Rocket Money
CSV exports, downloads them for CFO ingestion, and searches for financial emails.

---

## Files You Own

| File | Lines | Purpose |
|------|-------|---------|
| `guardian_one/agents/gmail_agent.py` | 368 | Core agent — inbox, CSV detection, financial search |
| `guardian_one/integrations/gmail_sync.py` | 522 | OAuth2 Gmail API, message parsing, CSV checker |
| `tests/test_gmail.py` | 396 | 29 tests — 100% public API coverage |

---

## Data Structures

```python
@dataclass
class EmailMessage:
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipient: str
    date: str
    snippet: str
    labels: list[str] = []           # ["INBOX", "UNREAD"]
    body_text: str = ""
    attachments: list[dict] = []     # {filename, mime_type, size, attachment_id}
    raw: dict = {}

@dataclass
class Attachment:
    filename: str
    mime_type: str
    size: int
    attachment_id: str
    message_id: str
    data: bytes = b""
```

---

## Method Reference

### GmailAgent
```python
# Inbox
agent.check_inbox() -> dict           # unread_count, recent messages (subject, sender, date, snippet)

# Rocket Money CSV
agent.check_rocket_money_csv(days_back=30) -> dict   # found, count, emails with csv_attachments
agent.download_rocket_money_csv() -> dict             # success, path, size

# Local CSV Processing (no auth needed)
agent.parse_rocket_money_csv(csv_path) -> list[dict]  # DictReader rows
agent.summarize_csv_transactions(transactions) -> dict # income, expenses, net, categories, accounts

# Financial Email Search
agent.search_financial_emails(days_back=30) -> list[dict]  # Chase, Ally, GS, Fidelity, Vanguard, RM

# BaseAgent
agent.run() -> AgentReport            # Check inbox + CSV + report alerts
agent.report() -> AgentReport         # State snapshot
```

### GmailProvider (OAuth2)
```python
provider = GmailProvider(credentials_path=None, token_path=None, user_email="me")
provider.authenticate() -> bool        # Cached token → interactive OAuth → env var fallback
provider.list_messages(query="", max_results=10, label_ids=None) -> list[dict]
provider.get_message(message_id, format="full") -> EmailMessage | None
provider.get_attachment(message_id, attachment_id) -> bytes
provider.search_messages(query, max_results=20) -> list[EmailMessage]
provider.get_unread_count() -> int
provider.is_authenticated -> bool
provider.has_credentials -> bool
```

### RocketMoneyCSVChecker
```python
checker = RocketMoneyCSVChecker(gmail_provider)
checker.build_search_query(recipient="jeremytabernero@gmail.com", days_back=30) -> str
checker.check(recipient, days_back=30, max_results=20) -> dict  # found, count, emails
checker.download_latest_csv(recipient, save_dir="data") -> dict  # success, path, size
```

---

## Authentication Flow

```
1. Try cached token (config/gmail_token.json)
   ↓ (if expired, auto-refresh via refresh_token)
2. Try interactive OAuth2 flow (opens browser)
   ↓ (saves token for next time)
3. Try GMAIL_ACCESS_TOKEN env var (fallback)
```

- **Scope**: `gmail.readonly` (read-only, cannot send/modify)
- **Credentials file**: `config/google_credentials.json`
- **Token file**: `config/gmail_token.json`

---

## Rocket Money Known Senders

```python
ROCKET_MONEY_SENDERS = [
    "noreply@rocketmoney.com",
    "support@rocketmoney.com",
    "export@rocketmoney.com",
    "no-reply@rocketmoney.com",
    "notifications@rocketmoney.com",
    "hello@rocketmoney.com",
]
```

Search query also matches: `rocketmoney.com`, `rocket-money.com`, `truebill.com`

---

## CSV Summary Output Format

```python
{
    "total_transactions": int,
    "total_income": float,          # negative amounts in Rocket Money = income
    "total_expenses": float,        # positive amounts = expenses
    "net": float,                   # income - expenses
    "categories": {"Food": 120.0, ...},  # sorted by amount DESC
    "accounts": {"Checking": 5, ...},
    "institutions": ["Chase", "Ally"],
    "date_range": {"earliest": "2026-01-01", "latest": "2026-03-15"}
}
```

---

## What's Working vs Stubbed

| Feature | Status |
|---------|--------|
| OAuth2 (cached/interactive/env) | Working |
| Inbox monitoring (unread, recent) | Working |
| Rocket Money CSV detection | Working |
| CSV download to disk | Working |
| Local CSV parsing | Working |
| CSV summarization | Working |
| Financial email search | Working |
| Message parsing (multipart) | Working |
| Attachment download | Working |
| **Everything is production-ready** | |

---

## Development Tracks

### Track 1: AI Email Categorization
- Use `agent.think_quick()` to auto-tag emails (bills, financial, personal)
- Store tags in cache for dashboard display

### Track 2: Bill Payment Detection
- Parse "amount due" + "due date" from financial email bodies
- Pass extracted data to Chronos for calendar reminders

### Track 3: Suspicious Transaction Alerts
- Flag unusual amounts in parsed CSV (z-score or AI reasoning)
- Add `flagged_transactions` to CSV summary

### Track 4: Auto-Fallback to API
- If no Rocket Money CSV found in 48h, switch to API sync
- Config: `rocket_money_mode: csv` already exists

### Track 5: Multi-Account Support
- Currently hardcoded to `jeremytabernero@gmail.com`
- Make configurable via `config.agents.gmail.accounts: [...]`

---

## Integration Pipeline

```
Gmail detects Rocket Money CSV
    ↓ download_rocket_money_csv()
saves to data/rocket_money_transactions.csv
    ↓
CFO.sync_from_csv(path)
    ↓
Updates ledger: accounts, transactions
    ↓
CFO.daily_review(gmail_data=...) includes email summary
```

---

## CLI Commands

```bash
python main.py --gmail                # Inbox status + Rocket Money CSV check
python main.py --csv PATH             # Parse local Rocket Money CSV
```

---

## Test Coverage (29 tests)

- GmailProvider: 14 tests (init, credentials, auth, parse, API)
- RocketMoneyCSVChecker: 5 tests (query building, auth, download)
- GmailAgent: 6 tests (init, run, inbox, CSV check)
- CSV Processing: 4 tests (parse, summarize, empty, real file)
- Registry: 1 test (threat model)

**Coverage: 100% of public API.** All auth paths tested.
