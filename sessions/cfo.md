# Session Handoff: CFO Agent (Financial Intelligence)

> Last updated: 2026-03-19
> Branch: `claude/guardian-one-system-4uvJv`

---

## What This Session Covers

You are working on **Guardian One's CFO agent** — the financial intelligence system
that manages accounts, transactions, bills, budgets, sync, reporting, and planning
for Jeremy Paulo Salvino Tabernero.

---

## Files You Own

| File | Lines | Purpose |
|------|-------|---------|
| `guardian_one/agents/cfo.py` | 1478 | **Core CFO agent** — all financial logic |
| `guardian_one/agents/cfo_dashboard.py` | 639 | Excel dashboard generation (4-sheet workbook) |
| `guardian_one/integrations/financial_sync.py` | 1151 | Plaid, Empower, Rocket Money providers |
| `tests/test_financial_sync.py` | 619 | 54 test cases for financial integrations |

**Related (touch but don't own):**
| File | Why |
|------|-----|
| `main.py` | CFO CLI commands (lines ~525-663) |
| `guardian_one/core/base_agent.py` | BaseAgent contract (initialize/run/report) |
| `guardian_one/core/ai_engine.py` | AI reasoning (think/think_quick) |

---

## CFO Capabilities — Complete Method Reference

### Account Management
```python
cfo.net_worth() -> float                          # Total across all accounts
cfo.balances_by_type() -> dict[str, float]        # Grouped by type (checking, savings, etc.)
cfo.get_account(name) -> Account | None           # Single account lookup
cfo.add_account(account, persist=True) -> None    # Add new account
cfo._accounts -> dict[str, Account]               # name → Account(name, type, balance, institution, last_synced)
```

### Transactions
```python
cfo.record_transaction(tx, persist=True) -> None
cfo.spending_summary(month=None) -> dict[str, float]   # category → total spent
cfo.income_summary(month=None) -> float                 # total income
cfo._transactions -> list[Transaction]                  # date, description, amount, category, account
```

### Bills
```python
cfo.add_bill(bill, persist=True) -> None
cfo.upcoming_bills(days=7) -> list[Bill]           # name, amount, due_date, recurring, auto_pay, paid
cfo.overdue_bills() -> list[Bill]                  # unpaid + past due
cfo.verify_bills_paid() -> list[dict]              # cross-check bills vs transactions
```

### Budgets
```python
cfo.set_budget(category, limit, label="", persist=True) -> Budget
cfo.remove_budget(category, persist=True) -> bool
cfo.budget_check(month=None) -> list[dict]         # category, limit, spent, remaining, percent_used, status
cfo.budget_alerts(month=None) -> list[str]         # plain-English alerts
```

### Verification & Reviews
```python
cfo.verify_transactions(days=7) -> dict            # checked, issues (duplicates, large, unknown, round), status
cfo.daily_review(gmail_data=None) -> dict          # transactions + bills + budget + overall_status
```

### Planning & Projections
```python
cfo.tax_recommendations() -> list[str]             # retirement, charitable, student loan tips
cfo.home_purchase_scenario(price, down_pct=0.20, rate=0.065, years=30) -> dict
cfo.create_scenario(scenario) -> None              # in-memory only (not persisted!)
cfo.record_net_worth(persist=True) -> None         # daily snapshot
cfo.net_worth_trend(months=12) -> list[dict]       # historical net worth
```

### Financial Sync (3 Providers)
```python
cfo.sync_all() -> dict                # Plaid → Empower → Rocket Money
cfo.sync_plaid() -> dict              # Read-only bank connections
cfo.sync_empower() -> dict            # Retirement/investment accounts
cfo.sync_rocket_money() -> dict       # Account aggregator + CSV fallback
cfo.sync_from_csv(path) -> dict       # Direct CSV import
```

### Reporting
```python
cfo.dashboard() -> dict               # Full financial snapshot
cfo.validation_report() -> dict       # Detailed report for presentation
cfo.generate_excel(output_path=None, password=None, gmail_data=None) -> Path
cfo.report() -> AgentReport           # BaseAgent structured report
```

### Provider Status
```python
cfo.rocket_money_status() -> dict
cfo.empower_status() -> dict
cfo.plaid_status() -> dict
```

---

## Financial Providers

### Rocket Money (Account Aggregator)
- **Auth**: OAuth bearer token via `/api/v1/health`
- **Features**: Fetch accounts + 90-day transactions
- **Fallback**: CSV import when API unavailable
- **Category mapping**: 153 upstream categories → 13 CFO categories
- **Account type mapping**: 12 RM types → 6 CFO types

### Empower (Retirement/Investment)
- **Auth**: API key or username/password
- **Features**: Fetch accounts, transactions, holdings, net worth history
- **Tracks**: 401k, IRA, Roth IRA, brokerage, HSA

### Plaid (Direct Bank Connections)
- **Auth**: Client ID + Secret + access tokens per institution
- **Security**: READ-ONLY enforced — 11 whitelisted endpoints only
- **Blocked**: `transfer`, `payment_initiation`, `deposit_switch`
- **Features**: Real-time balances, paginated transactions, investment holdings
- **Link flow**: Browser-based OAuth via separate link server

---

## Transaction Categories

```python
# 13 categories used throughout the system
CATEGORIES = [
    "income", "housing", "utilities", "food", "transport", "medical",
    "entertainment", "education", "insurance", "loan_payment",
    "savings", "charitable", "other"
]

# Friendly labels (CFO._CATEGORY_FRIENDLY)
FRIENDLY = {
    "income": "Income", "housing": "Housing / Rent", "utilities": "Utilities",
    "food": "Food & Groceries", "transport": "Transportation",
    "medical": "Medical / Health", "entertainment": "Shopping & Fun",
    "education": "Education", "insurance": "Insurance",
    "loan_payment": "Loan Payments", "savings": "Savings / Transfers",
    "charitable": "Donations", "other": "Other"
}
```

---

## Excel Dashboard (cfo_dashboard.py)

4-sheet professional workbook:

1. **Dashboard** (Blue) — KPIs, account table, budget status, upcoming bills, bar chart
2. **Expenses** (Orange) — Full transaction register with running totals, category dropdowns
3. **Budget** (Purple) — Budget vs Actual with live SUMIFS formulas, color coding
4. **Bills & Income** (Green) — Bill tracker + income section with totals

Features: Password protection, frozen panes, Excel formulas (not static), auto-filter, color-coded.

---

## Data Persistence

- **Ledger file**: `data/ledger.json` — accounts, transactions, bills, budgets, net worth snapshots
- **Plaid tokens**: `data/plaid_tokens.json` — encrypted access tokens per institution
- **CSV cache**: `data/` directory for Rocket Money CSV imports
- **Excel output**: `data/guardian_financial_dashboard.xlsx` (default)

---

## Test Coverage

**54 tests** in `test_financial_sync.py`:
- Category/account type mapping (5 tests)
- CSV parsing (4 tests)
- RocketMoneyProvider (5 tests)
- EmpowerProvider (8 tests)
- CFO + Rocket Money integration (6 tests)
- CFO + Empower integration (4 tests)
- PlaidProvider security (11 tests)
- CFO + Plaid integration (6 tests)
- Registry integration (2 tests)

**Not yet tested:**
- Transaction verification / fraud detection logic
- Daily review composition
- Bill verification (matching transactions to bills)
- Tax recommendations
- Home purchase scenario math
- Net worth trending
- Scenario creation
- Ledger save/load persistence
- Dashboard data aggregation
- Excel dashboard details

---

## Current Development Tracks

### Track A: Conversational Command Router (Spec Complete)
See `HANDOFF_CFO_ROUTER.md` — full spec for natural language queries:
```bash
python main.py --ask "what's my net worth?"
python main.py --chat   # interactive REPL
```
- 22 intents mapped to all CFO methods
- Deterministic keyword matching (works offline)
- Optional AI enhancement layer
- Text formatters for every intent
- Test plan with ~25 cases

### Track B: Expand Test Coverage
Missing coverage for:
- `verify_transactions()` fraud detection (duplicates, anomalies, new merchants, round numbers)
- `daily_review()` aggregation
- `verify_bills_paid()` cross-matching
- `tax_recommendations()` output
- `home_purchase_scenario()` math
- `net_worth_trend()` history
- `budget_check()` / `budget_alerts()` edge cases
- Ledger persistence (save/load cycle)
- Dashboard `generate_excel()` sheet structure

### Track C: Persistent Scenarios
`create_scenario()` stores in-memory only — lost on restart. Should persist to ledger JSON.

### Track D: Budget Forecasting
No projection of month-end balance based on spending trajectory. Could use
historical spending patterns + remaining days in month.

### Track E: Notion Financial Sync
Write-only push of financial summaries to Notion dashboard (similar to website sync).
Content gate must block all PII/PHI.

---

## CLI Commands (CFO-specific)

```bash
python main.py --dashboard                # Generate Excel dashboard
python main.py --validate                 # Validation report (for presentation)
python main.py --sync                     # Continuous financial sync loop
python main.py --sync-once               # Single sync cycle
python main.py --sync-interval N          # Set sync interval (seconds)
python main.py --connect                  # Plaid OAuth link server
python main.py --connect-port N           # Custom port for link server
python main.py --csv PATH                 # Parse Rocket Money CSV
python main.py --gmail                    # Gmail inbox + CSV detection
```

---

## Cross-Agent Integration Points

| Agent | Integration | Direction |
|-------|-------------|-----------|
| **Gmail** | Detects Rocket Money CSV exports → CFO ingests | Gmail → CFO |
| **Chronos** | Syncs bills to Google Calendar | CFO → Chronos |
| **DoorDash** | Checks meal budget against CFO budget | DoorDash → CFO |
| **WebArchitect** | Hosting costs tracked by CFO | WebArchitect → CFO |
| **Guardian** | Daily summary includes CFO financial status | CFO → Guardian |

---

## Key Data Structures

```python
@dataclass
class Account:
    name: str
    type: str           # checking, savings, credit_card, loan, investment, retirement
    balance: float
    institution: str
    last_synced: str    # ISO datetime

@dataclass
class Transaction:
    date: str           # YYYY-MM-DD
    description: str
    amount: float       # negative = expense, positive = income
    category: str       # one of 13 categories
    account: str        # account name

@dataclass
class Bill:
    name: str
    amount: float
    due_date: str       # YYYY-MM-DD
    recurring: bool
    auto_pay: bool
    paid: bool

@dataclass
class Budget:
    category: str
    limit: float
    label: str          # friendly display name
```
