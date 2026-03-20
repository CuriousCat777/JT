"""CFO Conversational Command Router.

Natural-language interface to Guardian One's CFO agent.
Keyword-based intent detection routes user queries to the
appropriate CFO methods, formats results, and optionally
enhances output with AI summaries.

Works fully without an AI backend — deterministic keyword
matching + structured formatters are the core.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from guardian_one.core.guardian import GuardianOne


@dataclass
class Intent:
    """Parsed user intent."""

    name: str
    confidence: float
    params: dict[str, Any] = field(default_factory=dict)
    raw_input: str = ""


@dataclass
class CommandResult:
    """Result of processing a command."""

    intent: Intent
    data: dict[str, Any]
    text: str
    ai_summary: str | None = None


# ── Intent definitions ────────────────────────────────────────────

_INTENT_REGISTRY: list[tuple[str, list[str], float]] = [
    # (intent_name, trigger_keywords, base_confidence)
    # Order matters — first match wins for equal-length matches,
    # but we pick the *longest keyword match* for accuracy.
    ("net_worth", ["net worth", "how much do i have", "total assets"], 0.9),
    ("accounts", ["my accounts", "account balances", "ledger", "show me my money"], 0.85),
    ("bills_overdue", ["overdue", "late bills", "missed bills"], 0.9),
    ("bills_upcoming", ["bills", "due", "upcoming", "what do i owe"], 0.85),
    ("spending", ["spending", "expenses", "where's my money going", "where is my money going"], 0.85),
    ("income", ["income", "earnings", "how much did i make", "paycheck"], 0.85),
    ("budget", ["budget", "on track", "over budget"], 0.85),
    ("transactions", ["transactions", "recent charges", "recent transactions"], 0.85),
    ("verify_transactions", ["verify transactions", "check transactions", "anomalies", "fraud"], 0.9),
    ("verify_bills", ["verify bills", "confirm payments"], 0.9),
    ("daily_review", ["daily review", "daily check", "morning report"], 0.9),
    ("dashboard", ["dashboard", "snapshot", "overview", "summary", "financial summary"], 0.85),
    ("tax", ["tax", "deductions", "retirement contributions"], 0.85),
    ("scenario_home", ["home purchase", "house", "mortgage", "afford"], 0.85),
    ("sync", ["sync", "refresh data", "update accounts", "pull data"], 0.85),
    ("excel", ["excel", "spreadsheet", "generate report"], 0.85),
    ("validate", ["validate", "validation report", "detailed report"], 0.85),
    ("net_worth_trend", ["net worth trend", "worth trend", "net worth history", "over time", "net worth progress"], 0.85),
    ("plaid_status", ["plaid", "bank connection"], 0.85),
    ("empower_status", ["empower", "retirement accounts"], 0.85),
    ("rocket_money_status", ["rocket money"], 0.85),
    ("set_budget", ["set budget", "budget to ", "budget limit"], 0.9),
    ("help", ["help", "what can you do", "commands"], 0.8),
]


class CommandRouter:
    """Routes natural-language queries to CFO methods."""

    def __init__(self, guardian: GuardianOne) -> None:
        self._guardian = guardian
        self._cfo = guardian.get_agent("cfo")
        self._ai = guardian.ai_engine

    # ── Public API ────────────────────────────────────────────────

    def handle(self, user_input: str) -> CommandResult:
        """Parse input -> detect intent -> execute -> format -> AI-enhance."""
        intent = self.detect_intent(user_input)
        data = self._execute(intent)
        text = self._format(intent, data)
        ai_summary = self._ai_enhance(intent, data, user_input)
        return CommandResult(intent=intent, data=data, text=text, ai_summary=ai_summary)

    # ── Intent Detection ──────────────────────────────────────────

    def detect_intent(self, text: str) -> Intent:
        """Keyword-based intent classification.

        Picks the intent whose trigger keyword is the longest match
        found in the lowered input. Falls back to 'help'.
        """
        lowered = text.lower().strip()
        best_name = "help"
        best_confidence = 0.0
        best_keyword_len = 0

        for intent_name, keywords, base_conf in _INTENT_REGISTRY:
            for kw in keywords:
                if kw in lowered and len(kw) > best_keyword_len:
                    best_name = intent_name
                    best_confidence = base_conf
                    best_keyword_len = len(kw)

        params = self._extract_params(lowered, best_name)
        return Intent(
            name=best_name,
            confidence=best_confidence,
            params=params,
            raw_input=text,
        )

    # ── Parameter Extraction ──────────────────────────────────────

    def _extract_params(self, text: str, intent: str) -> dict[str, Any]:
        """Extract parameters from natural language."""
        params: dict[str, Any] = {}

        # Month: "in march", "for january", "march 2026"
        month_match = re.search(
            r'\b(january|february|march|april|may|june|july|august|'
            r'september|october|november|december)\b',
            text,
        )
        if month_match:
            month_name = month_match.group(1)
            month_num = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12,
            }[month_name]
            year_match = re.search(r'\b(20\d{2})\b', text)
            year = int(year_match.group(1)) if year_match else datetime.now().year
            params["month"] = f"{year}-{month_num:02d}"

        # Days: "in 14 days", "next 30 days"
        days_match = re.search(r'(\d+)\s*days?', text)
        if days_match:
            params["days"] = int(days_match.group(1))

        # Price: "$350k", "$350,000", "350000"
        price_match = re.search(r'\$?([\d,]+)\s*k\b', text)
        if price_match:
            params["price"] = int(price_match.group(1).replace(",", "")) * 1000
        elif intent == "scenario_home":
            price_match2 = re.search(r'\$?([\d,]+)', text)
            if price_match2:
                val = int(price_match2.group(1).replace(",", ""))
                if val > 10000:
                    params["price"] = val

        # Count: "last 20 transactions"
        count_match = re.search(r'(?:last|recent|top)\s+(\d+)', text)
        if count_match:
            params["count"] = int(count_match.group(1))

        # Category + limit: "set food budget to 500"
        if intent == "set_budget":
            cat_match = re.search(
                r'(food|housing|utilities|transport|medical|entertainment|'
                r'education|insurance|loan_payment|savings|charitable|other)',
                text,
            )
            if cat_match:
                params["category"] = cat_match.group(1)
            limit_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)\s*$', text.strip())
            if not limit_match:
                limit_match = re.search(r'to\s+\$?([\d,]+(?:\.\d{2})?)', text)
            if limit_match:
                params["limit"] = float(limit_match.group(1).replace(",", ""))

        return params

    # ── Execution ─────────────────────────────────────────────────

    def _execute(self, intent: Intent) -> dict[str, Any]:
        """Call the appropriate CFO method and return structured data."""
        cfo = self._cfo
        if cfo is None:
            return {"error": "CFO agent not available"}

        name = intent.name
        params = intent.params

        try:
            if name == "net_worth":
                return {
                    "net_worth": cfo.net_worth(),
                    "by_type": cfo.balances_by_type(),
                }
            elif name == "accounts":
                return {
                    "accounts": [
                        {
                            "name": a.name,
                            "type": a.account_type.value if hasattr(a.account_type, "value") else str(a.account_type),
                            "balance": a.balance,
                            "institution": a.institution,
                        }
                        for a in cfo._accounts.values()
                    ]
                }
            elif name == "bills_upcoming":
                days = params.get("days", 7)
                bills = cfo.upcoming_bills(days=days)
                return {"bills": [{"name": b.name, "amount": b.amount, "due_date": b.due_date, "auto_pay": b.auto_pay} for b in bills]}
            elif name == "bills_overdue":
                bills = cfo.overdue_bills()
                return {"bills": [{"name": b.name, "amount": b.amount, "due_date": b.due_date} for b in bills]}
            elif name == "spending":
                month = params.get("month")
                return {"spending": cfo.spending_summary(month=month), "month": month}
            elif name == "income":
                month = params.get("month")
                return {"income": cfo.income_summary(month=month), "month": month}
            elif name == "budget":
                month = params.get("month")
                return {
                    "budget": cfo.budget_check(month=month),
                    "alerts": cfo.budget_alerts(month=month),
                }
            elif name == "transactions":
                count = params.get("count", 10)
                txns = cfo._transactions[-count:]
                return {
                    "transactions": [
                        {"date": t.date, "description": t.description, "amount": t.amount, "category": t.category.value if hasattr(t.category, "value") else str(t.category)}
                        for t in txns
                    ]
                }
            elif name == "verify_transactions":
                days = params.get("days", 7)
                return cfo.verify_transactions(days=days)
            elif name == "verify_bills":
                return {"results": cfo.verify_bills_paid()}
            elif name == "daily_review":
                return cfo.daily_review()
            elif name == "dashboard":
                return cfo.dashboard()
            elif name == "tax":
                return {"recommendations": cfo.tax_recommendations()}
            elif name == "scenario_home":
                price = params.get("price", 350000)
                return cfo.home_purchase_scenario(target_price=price)
            elif name == "sync":
                return cfo.sync_all()
            elif name == "excel":
                path = cfo.generate_excel()
                return {"path": str(path)}
            elif name == "validate":
                return cfo.validation_report()
            elif name == "net_worth_trend":
                return {"trend": cfo.net_worth_trend()}
            elif name == "plaid_status":
                return cfo.plaid_status()
            elif name == "empower_status":
                return cfo.empower_status()
            elif name == "rocket_money_status":
                return cfo.rocket_money_status()
            elif name == "set_budget":
                cat = params.get("category")
                limit = params.get("limit")
                if not cat or limit is None:
                    return {"error": "Need category and limit. Example: 'set food budget to 500'"}
                budget = cfo.set_budget(cat, limit)
                return {"category": budget.category, "limit": budget.limit, "label": budget.label}
            elif name == "help":
                return self._help_data()
            else:
                return self._help_data()
        except Exception as exc:
            return {"error": str(exc)}

    # ── Formatting ────────────────────────────────────────────────

    def _format(self, intent: Intent, data: dict[str, Any]) -> str:
        """Format structured data into readable CLI text."""
        if "error" in data:
            return f"  Error: {data['error']}"

        formatter = getattr(self, f"_format_{intent.name}", None)
        if formatter:
            return formatter(data)
        return self._format_generic(data)

    def _format_net_worth(self, data: dict[str, Any]) -> str:
        lines = [f"  Net Worth: ${data['net_worth']:,.2f}", ""]
        for atype, bal in data["by_type"].items():
            label = atype.replace("_", " ").title()
            lines.append(f"    {label + ':':20s} ${bal:>12,.2f}")
        return "\n".join(lines)

    def _format_accounts(self, data: dict[str, Any]) -> str:
        if not data["accounts"]:
            return "  No accounts on file."
        lines = ["  Accounts:"]
        for a in data["accounts"]:
            lines.append(f"    {a['name']:25s} ${a['balance']:>12,.2f}  ({a['institution']})")
        return "\n".join(lines)

    def _format_bills_upcoming(self, data: dict[str, Any]) -> str:
        bills = data["bills"]
        if not bills:
            return "  No upcoming bills."
        lines = ["  Upcoming Bills:"]
        for b in bills:
            auto = " (auto-pay)" if b.get("auto_pay") else ""
            lines.append(f"    {b['name']}: ${b['amount']:,.2f} — due {b['due_date']}{auto}")
        return "\n".join(lines)

    def _format_bills_overdue(self, data: dict[str, Any]) -> str:
        bills = data["bills"]
        if not bills:
            return "  No overdue bills."
        lines = ["  OVERDUE Bills:"]
        for b in bills:
            lines.append(f"    {b['name']}: ${b['amount']:,.2f} — was due {b['due_date']}")
        return "\n".join(lines)

    def _format_spending(self, data: dict[str, Any]) -> str:
        spending = data["spending"]
        month = data.get("month") or "current month"
        if not spending:
            return f"  No spending recorded for {month}."
        lines = [f"  Spending Summary ({month}):"]
        total = 0.0
        for cat, amount in sorted(spending.items(), key=lambda x: x[1], reverse=True):
            label = cat.replace("_", " ").title()
            lines.append(f"    {label + ':':20s} ${amount:>10,.2f}")
            total += amount
        lines.append(f"    {'Total:':20s} ${total:>10,.2f}")
        return "\n".join(lines)

    def _format_income(self, data: dict[str, Any]) -> str:
        month = data.get("month") or "current month"
        return f"  Income ({month}): ${data['income']:,.2f}"

    def _format_budget(self, data: dict[str, Any]) -> str:
        checks = data["budget"]
        alerts = data["alerts"]
        if not checks:
            return "  No budgets set."
        lines = ["  Budget Status:"]
        for b in checks:
            status_icon = "OK" if b["status"] == "ok" else "OVER" if b["status"] == "over" else "WARN"
            lines.append(
                f"    [{status_icon:4s}] {b.get('label', b['category']):20s} "
                f"${b['spent']:>8,.2f} / ${b['limit']:>8,.2f} ({b['percent_used']:.0f}%)"
            )
        if alerts:
            lines.append("")
            for a in alerts:
                lines.append(f"    [!] {a}")
        return "\n".join(lines)

    def _format_transactions(self, data: dict[str, Any]) -> str:
        txns = data["transactions"]
        if not txns:
            return "  No recent transactions."
        lines = ["  Recent Transactions:"]
        for t in txns:
            sign = "+" if t["amount"] > 0 else ""
            lines.append(f"    {t['date']}  {t['description']:30s} {sign}${t['amount']:>10,.2f}  [{t['category']}]")
        return "\n".join(lines)

    def _format_verify_transactions(self, data: dict[str, Any]) -> str:
        lines = [f"  Transaction Verification:"]
        lines.append(f"    Checked: {data.get('checked', 'N/A')}")
        lines.append(f"    Issues:  {data.get('issues', 0)}")
        lines.append(f"    Status:  {data.get('status', 'N/A')}")
        if data.get("summary"):
            lines.append(f"    Summary: {data['summary']}")
        return "\n".join(lines)

    def _format_verify_bills(self, data: dict[str, Any]) -> str:
        results = data["results"]
        if not results:
            return "  No bill verifications."
        lines = ["  Bill Verification:"]
        for r in results:
            status = "PAID" if r.get("paid") else "UNPAID"
            lines.append(f"    [{status}] {r.get('name', 'Unknown')}")
        return "\n".join(lines)

    def _format_daily_review(self, data: dict[str, Any]) -> str:
        lines = [f"  Daily Review — {data.get('overall_status', 'N/A')}"]
        if "transactions" in data:
            lines.append(f"    Transactions: {data['transactions']}")
        if "bills" in data:
            lines.append(f"    Bills: {data['bills']}")
        if "budget" in data:
            lines.append(f"    Budget: {data['budget']}")
        return "\n".join(lines)

    def _format_dashboard(self, data: dict[str, Any]) -> str:
        lines = ["  Financial Dashboard:"]
        for key, val in data.items():
            if isinstance(val, dict):
                lines.append(f"    {key}:")
                for k2, v2 in val.items():
                    lines.append(f"      {k2}: {v2}")
            elif isinstance(val, list):
                lines.append(f"    {key}: ({len(val)} items)")
            else:
                lines.append(f"    {key}: {val}")
        return "\n".join(lines)

    def _format_tax(self, data: dict[str, Any]) -> str:
        recs = data["recommendations"]
        if not recs:
            return "  No tax recommendations at this time."
        lines = ["  Tax Recommendations:"]
        for i, r in enumerate(recs, 1):
            lines.append(f"    {i}. {r}")
        return "\n".join(lines)

    def _format_scenario_home(self, data: dict[str, Any]) -> str:
        lines = ["  Home Purchase Scenario:"]
        for key, val in data.items():
            label = key.replace("_", " ").title()
            if isinstance(val, float):
                lines.append(f"    {label}: ${val:,.2f}")
            else:
                lines.append(f"    {label}: {val}")
        return "\n".join(lines)

    def _format_sync(self, data: dict[str, Any]) -> str:
        lines = ["  Sync Results:"]
        for provider, result in data.items():
            if isinstance(result, dict):
                status = result.get("status", "unknown")
                lines.append(f"    {provider}: {status}")
            else:
                lines.append(f"    {provider}: {result}")
        return "\n".join(lines)

    def _format_excel(self, data: dict[str, Any]) -> str:
        return f"  Excel dashboard saved: {data['path']}"

    def _format_validate(self, data: dict[str, Any]) -> str:
        lines = ["  Validation Report:"]
        for key, val in data.items():
            lines.append(f"    {key}: {val}")
        return "\n".join(lines)

    def _format_net_worth_trend(self, data: dict[str, Any]) -> str:
        trend = data["trend"]
        if not trend:
            return "  No net worth history recorded."
        lines = ["  Net Worth Trend:"]
        for entry in trend:
            lines.append(f"    {entry.get('date', '?')}: ${entry.get('net_worth', 0):,.2f}")
        return "\n".join(lines)

    def _format_plaid_status(self, data: dict[str, Any]) -> str:
        lines = ["  Plaid Status:"]
        for key, val in data.items():
            lines.append(f"    {key}: {val}")
        return "\n".join(lines)

    def _format_empower_status(self, data: dict[str, Any]) -> str:
        lines = ["  Empower Status:"]
        for key, val in data.items():
            lines.append(f"    {key}: {val}")
        return "\n".join(lines)

    def _format_rocket_money_status(self, data: dict[str, Any]) -> str:
        lines = ["  Rocket Money Status:"]
        for key, val in data.items():
            lines.append(f"    {key}: {val}")
        return "\n".join(lines)

    def _format_set_budget(self, data: dict[str, Any]) -> str:
        return f"  Budget set: {data.get('label', data.get('category'))} — ${data.get('limit', 0):,.2f}/month"

    def _format_help(self, data: dict[str, Any]) -> str:
        lines = ["  Guardian One — CFO Chat", ""]
        lines.append("  Available commands:")
        for cmd in data.get("commands", []):
            lines.append(f"    {cmd['example']:35s} {cmd['description']}")
        return "\n".join(lines)

    def _format_generic(self, data: dict[str, Any]) -> str:
        lines = []
        for key, val in data.items():
            lines.append(f"  {key}: {val}")
        return "\n".join(lines)

    # ── AI Enhancement ────────────────────────────────────────────

    def _ai_enhance(self, intent: Intent, data: dict[str, Any], user_input: str) -> str | None:
        """Optional AI narrative summary. Returns None if AI is unavailable."""
        if self._ai is None or "error" in data:
            return None

        system_prompt = (
            "You are the CFO of Guardian One, Jeremy's personal financial "
            "intelligence system. You have access to his complete financial picture. "
            "Respond conversationally but precisely. Always include exact dollar amounts. "
            "Never invent data — only summarize what's provided in the context."
        )

        try:
            response = self._ai.reason(
                agent_name="cfo_chat",
                prompt=f"Jeremy asked: '{user_input}'. Summarize this data for him.",
                system=system_prompt,
                context=data,
            )
            if response and hasattr(response, "text") and response.text:
                return response.text
            return None
        except Exception:
            return None

    # ── Help Data ─────────────────────────────────────────────────

    @staticmethod
    def _help_data() -> dict[str, Any]:
        return {
            "commands": [
                {"example": "what's my net worth?", "description": "Total net worth + breakdown"},
                {"example": "show me my accounts", "description": "All accounts with balances"},
                {"example": "any bills due?", "description": "Upcoming bills (next 7 days)"},
                {"example": "bills in 14 days", "description": "Upcoming bills (custom window)"},
                {"example": "any overdue bills?", "description": "Overdue/late bills"},
                {"example": "spending in march", "description": "Spending by category"},
                {"example": "how much did i make?", "description": "Income summary"},
                {"example": "how's my budget?", "description": "Budget status + alerts"},
                {"example": "last 20 transactions", "description": "Recent transactions"},
                {"example": "verify transactions", "description": "Check for anomalies"},
                {"example": "verify bills", "description": "Confirm bill payments"},
                {"example": "daily review", "description": "Full daily financial check"},
                {"example": "dashboard", "description": "Financial snapshot"},
                {"example": "tax recommendations", "description": "Tax optimization tips"},
                {"example": "can I afford a $350k house?", "description": "Home purchase scenario"},
                {"example": "sync", "description": "Refresh all account data"},
                {"example": "generate excel", "description": "Export Excel dashboard"},
                {"example": "validation report", "description": "Detailed validation"},
                {"example": "net worth trend", "description": "Historical net worth"},
                {"example": "plaid status", "description": "Bank connection status"},
                {"example": "empower status", "description": "Retirement account status"},
                {"example": "rocket money status", "description": "Rocket Money status"},
                {"example": "set food budget to 500", "description": "Set a budget limit"},
                {"example": "help", "description": "Show this help"},
            ]
        }
