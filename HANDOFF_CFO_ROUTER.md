# HANDOFF: CFO Conversational Command Router

> Session: 2026-03-19
> Status: **SPEC COMPLETE — READY TO BUILD**
> Branch: `claude/guardian-one-system-4uvJv`

---

## Goal

Build a natural language command router that lets Jeremy talk to Guardian One
conversationally and have it execute CFO actions. Example:

```
python main.py --ask "what's my net worth?"
python main.py --ask "any bills due this week?"
python main.py --ask "how's my budget looking?"
python main.py --chat   # interactive REPL
```

---

## Architecture

### New Files to Create

```
guardian_one/core/command_router.py    # Intent parser + action dispatcher
tests/test_command_router.py           # Full test coverage
```

### Files to Modify

```
main.py                                # Add --ask and --chat CLI entry points
```

---

## Design: `command_router.py`

### Intent Detection (Deterministic — no AI needed for routing)

The router uses keyword/pattern matching to classify user input into intents.
This ensures it works even when the AI engine is offline.

```python
@dataclass
class Intent:
    name: str           # e.g. "net_worth", "bills_upcoming"
    confidence: float   # 0.0–1.0
    params: dict        # extracted params like {"month": "2026-03"}
    raw_input: str      # original user text

@dataclass
class CommandResult:
    intent: Intent
    data: dict[str, Any]       # structured data from CFO
    text: str                  # plain-English formatted output
    ai_summary: str | None     # AI-enhanced narrative (if engine available)
```

### Intent Registry — Full CFO Coverage

| Intent ID | Trigger Keywords | CFO Method | Returns |
|-----------|-----------------|------------|---------|
| `net_worth` | "net worth", "how much do i have", "total" | `cfo.net_worth()` + `cfo.balances_by_type()` | Dollar amount + breakdown |
| `accounts` | "accounts", "balances", "ledger", "show me my money" | `cfo._accounts` | All accounts with balances |
| `bills_upcoming` | "bills", "due", "upcoming", "what do i owe" | `cfo.upcoming_bills(days)` | List of upcoming bills |
| `bills_overdue` | "overdue", "late", "missed" | `cfo.overdue_bills()` | Overdue bills |
| `spending` | "spending", "expenses", "where's my money going" | `cfo.spending_summary(month)` | Category breakdown |
| `income` | "income", "earnings", "how much did i make" | `cfo.income_summary(month)` | Total income |
| `budget` | "budget", "on track", "over budget" | `cfo.budget_check()` + `cfo.budget_alerts()` | Budget status + alerts |
| `transactions` | "transactions", "recent charges" | `cfo._transactions[-N:]` | Recent transaction list |
| `verify_transactions` | "verify", "check transactions", "anomalies", "fraud" | `cfo.verify_transactions(days)` | Verification report |
| `verify_bills` | "verify bills", "confirm payments" | `cfo.verify_bills_paid()` | Bill verification |
| `daily_review` | "daily review", "daily check", "morning report" | `cfo.daily_review()` | Full daily review |
| `dashboard` | "dashboard", "snapshot", "overview", "summary" | `cfo.dashboard()` | Full financial snapshot |
| `tax` | "tax", "deductions", "retirement contributions" | `cfo.tax_recommendations()` | Tax optimization tips |
| `scenario_home` | "home purchase", "house", "mortgage", "afford" | `cfo.home_purchase_scenario(price)` | Affordability projection |
| `sync` | "sync", "refresh", "update accounts", "pull data" | `cfo.sync_all()` | Sync results |
| `excel` | "excel", "spreadsheet", "generate report" | `cfo.generate_excel()` | Path to generated file |
| `validate` | "validate", "validation report", "detailed report" | `cfo.validation_report()` | Full validation |
| `net_worth_trend` | "trend", "history", "over time", "progress" | `cfo.net_worth_trend()` | Historical net worth |
| `plaid_status` | "plaid", "bank connection" | `cfo.plaid_status()` | Plaid status |
| `empower_status` | "empower", "retirement" | `cfo.empower_status()` | Empower status |
| `rocket_money_status` | "rocket money" | `cfo.rocket_money_status()` | RM status |
| `set_budget` | "set budget", "budget limit" | `cfo.set_budget(cat, limit)` | Confirmation |
| `help` | "help", "what can you do", "commands" | N/A | List of capabilities |

### Parameter Extraction

The router should extract parameters from natural language:

- **Month**: "spending in March" → `{"month": "2026-03"}`
- **Days**: "bills due in 14 days" → `{"days": 14}`
- **Price**: "can I afford a $350k house" → `{"price": 350000}`
- **Category**: "set food budget to $500" → `{"category": "food", "limit": 500}`
- **Count**: "last 20 transactions" → `{"count": 20}`

### AI Enhancement (Optional Layer)

When the AI engine IS available, the router wraps structured data with a
conversational summary via `guardian.ai_engine.reason()`:

```python
system_prompt = """You are the CFO of Guardian One, Jeremy's personal financial
intelligence system. You have access to his complete financial picture.
Respond conversationally but precisely. Always include exact dollar amounts.
Never invent data — only summarize what's provided in the context."""

# After getting structured data from CFO methods:
ai_response = ai_engine.reason(
    agent_name="cfo_chat",
    prompt=f"Jeremy asked: '{user_input}'. Summarize this data for him.",
    system=system_prompt,
    context=structured_data,
)
```

When AI is offline, fall back to the plain-text formatter (still useful).

---

## Design: Text Formatters (No-AI Fallback)

Every intent needs a `_format_<intent>()` method that produces readable CLI output
from the structured data. Examples:

```python
def _format_net_worth(self, data: dict) -> str:
    lines = [f"  Net Worth: ${data['net_worth']:,.2f}", ""]
    for atype, bal in data["by_type"].items():
        label = atype.replace("_", " ").title()
        lines.append(f"    {label + ':':20s} ${bal:>12,.2f}")
    return "\n".join(lines)

def _format_bills_upcoming(self, bills: list) -> str:
    if not bills:
        return "  No upcoming bills."
    lines = ["  Upcoming Bills:"]
    for b in bills:
        lines.append(f"    {b['name']}: ${b['amount']:,.2f} — due {b['due_date']}")
    return "\n".join(lines)
```

---

## Design: CLI Integration (`main.py`)

### `--ask` (single query)

```python
parser.add_argument("--ask", type=str, help="Ask Guardian a question")
```

```python
elif args.ask:
    from guardian_one.core.command_router import CommandRouter
    router = CommandRouter(guardian)
    result = router.handle(args.ask)
    print(result.text)
    if result.ai_summary:
        print(f"\n  {result.ai_summary}")
```

### `--chat` (interactive REPL)

```python
parser.add_argument("--chat", action="store_true", help="Interactive chat with Guardian")
```

```python
elif args.chat:
    from guardian_one.core.command_router import CommandRouter
    router = CommandRouter(guardian)
    print("  Guardian One — CFO Chat")
    print("  Type 'quit' to exit, 'help' for commands.\n")
    while True:
        try:
            user_input = input("  You > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "bye"):
                print("  Guardian signing off.")
                break
            result = router.handle(user_input)
            print(f"\n{result.text}")
            if result.ai_summary:
                print(f"\n  {result.ai_summary}")
            print()
        except (KeyboardInterrupt, EOFError):
            print("\n  Guardian signing off.")
            break
```

---

## Design: `CommandRouter` Class Structure

```python
class CommandRouter:
    def __init__(self, guardian: GuardianOne) -> None:
        self._guardian = guardian
        self._cfo: CFO = guardian.get_agent("cfo")  # type: ignore
        self._ai = guardian.ai_engine
        self._intents = self._build_intent_registry()

    def handle(self, user_input: str) -> CommandResult:
        """Parse input → detect intent → execute → format → optionally AI-enhance."""
        intent = self._detect_intent(user_input)
        data = self._execute(intent)
        text = self._format(intent, data)
        ai_summary = self._ai_enhance(intent, data, user_input)
        return CommandResult(intent=intent, data=data, text=text, ai_summary=ai_summary)

    def _detect_intent(self, text: str) -> Intent:
        """Keyword-based intent classification."""
        ...

    def _execute(self, intent: Intent) -> dict:
        """Call the appropriate CFO method."""
        ...

    def _format(self, intent: Intent, data: dict) -> str:
        """Format structured data into readable CLI text."""
        ...

    def _ai_enhance(self, intent: Intent, data: dict, user_input: str) -> str | None:
        """Optional AI narrative summary."""
        ...
```

---

## Test Plan: `tests/test_command_router.py`

### Intent Detection Tests
```
test_detect_net_worth_intent — "what's my net worth?" → net_worth
test_detect_bills_intent — "any bills due?" → bills_upcoming
test_detect_spending_intent — "where's my money going?" → spending
test_detect_budget_intent — "how's my budget?" → budget
test_detect_sync_intent — "sync my accounts" → sync
test_detect_help_intent — "what can you do?" → help
test_detect_unknown_intent — "blah blah" → help (fallback)
```

### Parameter Extraction Tests
```
test_extract_month — "spending in march" → month=2026-03
test_extract_days — "bills in 14 days" → days=14
test_extract_price — "afford a 350k house" → price=350000
test_extract_category_and_limit — "set food budget to 500" → category=food, limit=500
test_extract_count — "last 20 transactions" → count=20
```

### Execution Tests (with fake CFO)
```
test_execute_net_worth — returns formatted net worth
test_execute_bills_upcoming — returns bill list
test_execute_spending_summary — returns category breakdown
test_execute_budget_check — returns budget status
test_execute_daily_review — returns full review
test_execute_verify_transactions — returns verification report
test_execute_sync — triggers sync_all and returns results
test_execute_excel — generates excel and returns path
```

### Formatting Tests
```
test_format_net_worth — dollar amounts aligned
test_format_bills_empty — "No upcoming bills."
test_format_budget_alerts — shows over-budget warnings
```

### AI Enhancement Tests
```
test_ai_enhance_when_available — returns narrative summary
test_ai_enhance_when_offline — returns None gracefully
```

### Integration Tests
```
test_full_handle_pipeline — input → intent → execute → format → result
test_chat_help_command — lists all capabilities
test_unknown_input_falls_back — doesn't crash, shows help
```

---

## Key Files Already Read (for context)

| File | Lines | What You Need |
|------|-------|---------------|
| `guardian_one/agents/cfo.py` | 1478 | **ALL CFO methods** — net_worth, balances_by_type, spending_summary, income_summary, upcoming_bills, overdue_bills, budget_check, budget_alerts, set_budget, remove_budget, verify_transactions, verify_bills_paid, daily_review, tax_recommendations, home_purchase_scenario, sync_rocket_money, sync_empower, sync_plaid, sync_all, dashboard, generate_excel, validation_report, record_net_worth, net_worth_trend, rocket_money_status, empower_status, plaid_status |
| `guardian_one/core/ai_engine.py` | 484 | `AIEngine.reason(agent_name, prompt, system, context)` and `reason_stateless()` |
| `guardian_one/core/guardian.py` | ~300 | `guardian.ai_engine`, `guardian.get_agent("cfo")` |
| `main.py` | 1067 | All CLI args — add `--ask` and `--chat` |

---

## CFO Method Signatures (Quick Reference)

```python
# Account data
cfo.net_worth() -> float
cfo.balances_by_type() -> dict[str, float]
cfo.get_account(name) -> Account | None
cfo._accounts -> dict[str, Account]  # name → Account(name, type, balance, institution, last_synced)

# Transactions
cfo.spending_summary(month: str | None) -> dict[str, float]  # category → amount
cfo.income_summary(month: str | None) -> float
cfo._transactions -> list[Transaction]  # date, description, amount, category, account

# Bills
cfo.upcoming_bills(days=7) -> list[Bill]  # name, amount, due_date, recurring, auto_pay, paid
cfo.overdue_bills() -> list[Bill]
cfo.verify_bills_paid() -> list[dict]

# Budget
cfo.budget_check(month=None) -> list[dict]  # category, label, limit, spent, remaining, percent_used, status
cfo.budget_alerts(month=None) -> list[str]
cfo.set_budget(category, limit, label="") -> Budget
cfo.remove_budget(category) -> bool

# Verification
cfo.verify_transactions(days=7) -> dict  # checked, issues, summary, status
cfo.daily_review(gmail_data=None) -> dict  # transactions, bills, budget, overall_status

# Planning
cfo.tax_recommendations() -> list[str]
cfo.home_purchase_scenario(price, down_pct=0.20, rate=0.065, term=30) -> dict
cfo.net_worth_trend(months=12) -> list[dict]

# Sync
cfo.sync_all() -> dict
cfo.sync_rocket_money() -> dict
cfo.sync_empower() -> dict
cfo.sync_plaid() -> dict

# Reports
cfo.dashboard() -> dict  # full financial snapshot
cfo.validation_report() -> dict  # detailed validation
cfo.generate_excel(output_path=None, password=None, gmail_data=None) -> Path

# Status
cfo.rocket_money_status() -> dict
cfo.empower_status() -> dict
cfo.plaid_status() -> dict
```

---

## TransactionCategory Values (for budget/spending mapping)

```
income, housing, utilities, food, transport, medical,
entertainment, education, insurance, loan_payment, savings, charitable, other
```

## Friendly Labels (already in CFO._CATEGORY_FRIENDLY)

```python
"income": "Income", "housing": "Housing / Rent", "utilities": "Utilities",
"food": "Food & Groceries", "transport": "Transportation",
"medical": "Medical / Health", "entertainment": "Shopping & Fun",
"education": "Education", "insurance": "Insurance",
"loan_payment": "Loan Payments", "savings": "Savings / Transfers",
"charitable": "Donations", "other": "Other"
```

---

## Implementation Order

1. Create `guardian_one/core/command_router.py` with all intents + formatters
2. Create `tests/test_command_router.py` with full coverage
3. Add `--ask` and `--chat` to `main.py`
4. Run `pytest tests/ -v` — all 200+ existing tests must still pass
5. Commit and push to `claude/guardian-one-system-4uvJv`

---

## Principle: Works Without AI

The router MUST work fully without an AI backend. The AI layer is a
nice-to-have that adds conversational polish. Deterministic keyword matching
+ structured formatters = the core. This means Jeremy can always ask
"what's my net worth?" and get an answer, even on a plane with no internet
and no Ollama running.
