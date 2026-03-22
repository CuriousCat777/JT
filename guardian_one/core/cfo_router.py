"""CFO Conversational Command Router.

Routes natural-language user queries to the correct CFO agent method.
Uses keyword matching and regex patterns — no LLM required at runtime.

Usage:
    from guardian_one.core.cfo_router import CFORouter

    router = CFORouter(cfo)
    result = router.handle("what's my net worth?")
    print(result.text)

Or as a REPL:
    python main.py --cfo
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from guardian_one.agents.cfo import CFO


@dataclass
class RouteResult:
    """Structured response from a routed command."""
    intent: str
    text: str
    data: dict[str, Any] = field(default_factory=dict)
    success: bool = True


@dataclass
class Route:
    """A single intent-to-handler mapping."""
    intent: str
    keywords: list[str]
    handler: Callable[[str], RouteResult]
    patterns: list[re.Pattern[str]] = field(default_factory=list)
    description: str = ""
    priority: int = 0  # Higher = matched first on ties


class CFORouter:
    """Maps natural-language queries to CFO agent methods.

    Scoring: each route gets a score based on how many of its keywords
    appear in the user input.  Regex patterns provide an automatic match
    (score = 100) when they fire.  The highest-scoring route wins.
    """

    def __init__(self, cfo: "CFO") -> None:
        self._cfo = cfo
        self._routes: list[Route] = []
        self._register_routes()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle(self, user_input: str) -> RouteResult:
        """Route a natural-language query to the best-matching handler."""
        cleaned = user_input.strip()
        if not cleaned:
            return RouteResult(
                intent="empty",
                text="What would you like to know? Try 'help' to see what I can do.",
                success=False,
            )

        lower = cleaned.lower()

        # Check for help / exit first
        if lower in ("help", "?", "commands", "what can you do"):
            return self._help(cleaned)
        if lower in ("exit", "quit", "bye", "q"):
            return RouteResult(intent="exit", text="Goodbye.", data={"exit": True})

        best_route: Route | None = None
        best_score = 0

        for route in self._routes:
            score = self._score(lower, route)
            if score > best_score:
                best_score = score
                best_route = route

        if best_route and best_score >= 1:
            try:
                return best_route.handler(cleaned)
            except Exception as exc:
                return RouteResult(
                    intent=best_route.intent,
                    text=f"Error running {best_route.intent}: {exc}",
                    success=False,
                )

        return RouteResult(
            intent="unknown",
            text=(
                f"I don't have a handler for that yet. I'm the CFO financial module —\n"
                f"I can answer questions about your money, bills, budget, and accounts.\n\n"
                f"Try: 'net worth', 'show bills', 'spending', 'who are you', or 'help'"
            ),
            success=False,
        )

    def list_intents(self) -> list[dict[str, str]]:
        """Return all registered intents with descriptions."""
        return [
            {"intent": r.intent, "description": r.description}
            for r in sorted(self._routes, key=lambda r: r.intent)
        ]

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _score(text: str, route: Route) -> int:
        """Score how well *text* matches a route.

        Returns:
            0   — no match
            1+  — keyword match count + priority bonus
            100 — regex pattern matched (guaranteed route)
        """
        # Regex patterns are auto-win
        for pat in route.patterns:
            if pat.search(text):
                return 100 + route.priority

        # Keyword scoring
        hits = sum(1 for kw in route.keywords if kw in text)
        if hits == 0:
            return 0
        return hits + route.priority

    # ------------------------------------------------------------------
    # Route registration
    # ------------------------------------------------------------------

    def _register_routes(self) -> None:
        """Build the routing table."""

        # --- Net worth ---
        self._routes.append(Route(
            intent="net_worth",
            keywords=["net worth", "net-worth", "total worth", "how much do i have",
                       "total balance", "what am i worth"],
            patterns=[re.compile(r"net\s*worth(?!\s*(trend|history|progress|over time))", re.I)],
            handler=self._net_worth,
            description="Show your current net worth",
            priority=2,
        ))

        # --- Dashboard / overview ---
        self._routes.append(Route(
            intent="dashboard",
            keywords=["dashboard", "overview", "snapshot", "financial summary",
                       "summary", "how am i doing", "status"],
            patterns=[re.compile(r"(financial\s+)?(dashboard|overview|snapshot)", re.I)],
            handler=self._dashboard,
            description="Full financial overview (accounts, spending, bills, budget)",
            priority=1,
        ))

        # --- Accounts ---
        self._routes.append(Route(
            intent="accounts",
            keywords=["accounts", "account list", "bank accounts", "balances",
                       "show accounts", "my accounts", "account balances"],
            patterns=[re.compile(r"(show|list|my)\s+accounts?", re.I)],
            handler=self._accounts,
            description="List all accounts and balances",
        ))

        # --- Spending ---
        self._routes.append(Route(
            intent="spending",
            keywords=["spending", "expenses", "spent", "how much did i spend",
                       "where is my money going", "expense breakdown", "expenditures"],
            patterns=[
                re.compile(r"(how much|what).*(spend|spent)", re.I),
                re.compile(r"spending\s+(summary|breakdown|report)", re.I),
            ],
            handler=self._spending,
            description="Monthly spending breakdown by category",
        ))

        # --- Income ---
        self._routes.append(Route(
            intent="income",
            keywords=["income", "earnings", "how much did i earn", "salary",
                       "how much did i make", "paychecks"],
            patterns=[re.compile(r"(how much|what).*(earn|income|make|made)", re.I)],
            handler=self._income,
            description="Monthly income total",
        ))

        # --- Bills ---
        self._routes.append(Route(
            intent="bills",
            keywords=["bills", "upcoming bills", "due", "overdue",
                       "what do i owe", "payments due", "bill status"],
            patterns=[
                re.compile(r"(upcoming|overdue|next)\s+bills?", re.I),
                re.compile(r"what.*(owe|due|bills?)", re.I),
            ],
            handler=self._bills,
            description="Upcoming and overdue bills",
            priority=1,
        ))

        # --- Budget ---
        self._routes.append(Route(
            intent="budget",
            keywords=["budget", "budget check", "am i over budget",
                       "budget status", "spending limits", "budget vs actual"],
            patterns=[re.compile(r"budget\s*(check|status|vs|report)?", re.I)],
            handler=self._budget,
            description="Budget vs actual spending",
        ))

        # --- Daily review ---
        self._routes.append(Route(
            intent="daily_review",
            keywords=["daily review", "daily check", "anything i should know",
                       "morning briefing", "daily briefing", "what needs attention"],
            patterns=[re.compile(r"daily\s+(review|check|brief)", re.I)],
            handler=self._daily_review,
            description="Full daily financial review",
            priority=1,
        ))

        # --- Tax ---
        self._routes.append(Route(
            intent="tax",
            keywords=["tax", "taxes", "tax recommendations", "tax advice",
                       "tax optimization", "tax tips", "deductions"],
            patterns=[re.compile(r"tax\s*(recommend|optim|advi|tip|deduct)?", re.I)],
            handler=self._tax,
            description="Tax optimization recommendations",
        ))

        # --- Home purchase scenario ---
        self._routes.append(Route(
            intent="home_scenario",
            keywords=["home purchase", "buy a house", "mortgage", "house",
                       "home affordability", "can i afford"],
            patterns=[
                re.compile(r"(home|house)\s*(purchase|buy|afford|scenario)", re.I),
                re.compile(r"mortgage\s*(calc|scenario)?", re.I),
                re.compile(r"can i (afford|buy)\s*(a\s+)?(home|house)", re.I),
            ],
            handler=self._home_scenario,
            description="Home purchase affordability scenario",
        ))

        # --- Net worth trend ---
        self._routes.append(Route(
            intent="trend",
            keywords=["trend", "net worth trend", "progress", "trajectory",
                       "net worth history", "track record", "over time"],
            patterns=[re.compile(r"(net worth|wealth)\s*(trend|history|progress|over time)", re.I)],
            handler=self._trend,
            description="Net worth trend over time",
            priority=3,
        ))

        # --- Sync status ---
        self._routes.append(Route(
            intent="sync_status",
            keywords=["sync", "sync status", "plaid", "rocket money status",
                       "empower status", "bank connection", "connected banks"],
            patterns=[re.compile(r"sync\s*status", re.I)],
            handler=self._sync_status,
            description="Status of bank sync connections (Plaid, Empower, Rocket Money)",
        ))

        # --- Generate Excel ---
        self._routes.append(Route(
            intent="excel",
            keywords=["excel", "spreadsheet", "generate dashboard", "xlsx",
                       "export", "download dashboard", "generate excel"],
            patterns=[
                re.compile(r"(generate|create|export|make|save)\s+.*(excel|xlsx|spreadsheet)", re.I),
                re.compile(r"(excel|xlsx|spreadsheet)", re.I),
            ],
            handler=self._excel,
            description="Generate the Excel financial dashboard",
            priority=5,
        ))

        # --- Validation report ---
        self._routes.append(Route(
            intent="validate",
            keywords=["validate", "validation", "validation report", "verify",
                       "audit", "financial audit"],
            patterns=[re.compile(r"valid(ate|ation)\s*report?", re.I)],
            handler=self._validate,
            description="Detailed CFO validation report",
        ))

        # --- Recent transactions ---
        self._routes.append(Route(
            intent="transactions",
            keywords=["transactions", "recent transactions", "transaction history",
                       "last transactions", "show transactions", "what did i buy"],
            patterns=[
                re.compile(r"(recent|last|show)\s*transactions?", re.I),
                re.compile(r"what did i (buy|purchase)", re.I),
            ],
            handler=self._transactions,
            description="Recent transactions",
        ))

        # --- About / identity ---
        self._routes.append(Route(
            intent="about",
            keywords=["who are you", "what are you", "about", "self hosted",
                       "ai agent", "are you", "guardian"],
            patterns=[
                re.compile(r"(who|what)\s+are\s+you", re.I),
                re.compile(r"(self[- ]?hosted|ai\s*agent)", re.I),
                re.compile(r"are you.*(ai|agent|bot|guardian)", re.I),
            ],
            handler=self._about,
            description="About this financial assistant",
        ))

        # --- Data source ---
        self._routes.append(Route(
            intent="data_source",
            keywords=["where", "data", "source", "getting your data",
                       "data from", "how do you know", "where does"],
            patterns=[
                re.compile(r"where.*(data|info|getting|come from|source)", re.I),
                re.compile(r"(data|info)\s*(source|from|come)", re.I),
                re.compile(r"how do you know", re.I),
            ],
            handler=self._data_source,
            description="Where your financial data comes from",
            priority=3,
        ))

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _help(self, _: str) -> RouteResult:
        lines = ["Here's what I can help with:\n"]
        for r in sorted(self._routes, key=lambda r: r.intent):
            lines.append(f"  {r.intent:<20s} — {r.description}")
        lines.append("\nJust ask naturally — e.g. 'what's my net worth?' or 'show my bills'.")
        lines.append("Type 'exit' or 'quit' to leave.")
        return RouteResult(intent="help", text="\n".join(lines))

    def _about(self, _: str) -> RouteResult:
        return RouteResult(
            intent="about",
            text=(
                "I'm the CFO module of Guardian One — Jeremy's multi-agent AI system.\n"
                "I run locally on this machine (not cloud-hosted). No financial data\n"
                "leaves your computer unless you explicitly sync to an external service.\n\n"
                "I manage: accounts, transactions, bills, budgets, tax planning,\n"
                "and scenario modeling. I pull data from Plaid (direct bank connections),\n"
                "Empower (retirement), and Rocket Money (account aggregation).\n\n"
                "Type 'data source' for details on where your data comes from,\n"
                "or 'sync status' to check which providers are connected."
            ),
        )

    def _data_source(self, _: str) -> RouteResult:
        plaid = self._cfo.plaid_status()
        rm = self._cfo.rocket_money_status()
        emp = self._cfo.empower_status()

        lines = [
            "Your financial data comes from these sources:\n",
            f"  1. Plaid (direct bank API)  — {'connected' if plaid.get('connected') else 'offline'}"
            f" ({plaid.get('connected_institutions', 0)} bank(s))",
            f"  2. Empower (retirement)     — {'connected' if emp.get('connected') else 'offline'}",
            f"  3. Rocket Money (aggregator) — {'connected' if rm.get('connected') else 'offline'}"
            f" (mode: {rm.get('sync_mode', 'n/a')})",
            "",
            "All data is stored locally in:",
            f"  Ledger: {self._cfo._ledger_path}",
            f"  Accounts: {len(self._cfo._accounts)} | Transactions: {len(self._cfo._transactions)}",
            "",
            f"Last saved: {self._cfo._last_sync or 'check ledger file'}",
            "",
            "Nothing is sent to the cloud. Guardian One runs entirely on this machine.",
        ]
        return RouteResult(
            intent="data_source",
            text="\n".join(lines),
            data={"plaid": plaid, "rocket_money": rm, "empower": emp},
        )

    def _net_worth(self, _: str) -> RouteResult:
        nw = self._cfo.net_worth()
        by_type = self._cfo.balances_by_type()

        lines = [f"Net Worth: ${nw:,.2f}\n"]
        if by_type:
            lines.append("Breakdown:")
            for atype, total in sorted(by_type.items()):
                label = atype.replace("_", " ").title()
                lines.append(f"  {label:<20s} ${total:>12,.2f}")

        return RouteResult(
            intent="net_worth",
            text="\n".join(lines),
            data={"net_worth": nw, "by_type": by_type},
        )

    def _dashboard(self, _: str) -> RouteResult:
        d = self._cfo.dashboard()
        nw = d["net_worth"]
        lines = [
            f"Financial Dashboard",
            f"{'=' * 50}",
            f"  Net Worth:     ${nw:>12,.2f}",
        ]

        for atype, bal in d.get("balances_by_type", {}).items():
            label = atype.replace("_", " ").title()
            lines.append(f"  {label + ':':15s} ${bal:>12,.2f}")

        lines.append(f"\n  Income (this month):  ${d.get('income_this_month', 0):>10,.2f}")

        spending = d.get("spending_this_month", {})
        total_spent = sum(spending.values())
        lines.append(f"  Spending (this month): ${total_spent:>10,.2f}")
        lines.append(f"  Left over:            ${d.get('income_this_month', 0) - total_spent:>10,.2f}")

        overdue = d.get("overdue_bills", [])
        if overdue:
            lines.append(f"\n  [!!] {len(overdue)} OVERDUE bill(s):")
            for b in overdue:
                lines.append(f"    {b['name']}: ${b['amount']:.2f} — due {b['due']}")

        upcoming = d.get("upcoming_bills", [])
        if upcoming:
            lines.append(f"\n  Upcoming bills ({len(upcoming)}):")
            for b in upcoming:
                lines.append(f"    {b['name']}: ${b['amount']:.2f} — due {b['due']}")

        alerts = d.get("budget_alerts", [])
        if alerts:
            lines.append(f"\n  Budget alerts:")
            for a in alerts:
                lines.append(f"    [!] {a}")

        return RouteResult(intent="dashboard", text="\n".join(lines), data=d)

    def _accounts(self, _: str) -> RouteResult:
        accounts = sorted(self._cfo._accounts.values(), key=lambda a: -a.balance)
        if not accounts:
            return RouteResult(
                intent="accounts",
                text="No accounts on file yet. Run a sync to pull account data.",
            )

        lines = [f"{'Account':<40s} {'Type':<15s} {'Balance':>12s}"]
        lines.append("-" * 69)
        for a in accounts:
            atype = a.account_type.value.replace("_", " ").title()
            lines.append(f"{a.name:<40s} {atype:<15s} ${a.balance:>11,.2f}")
        lines.append("-" * 69)
        lines.append(f"{'TOTAL':<40s} {'':15s} ${self._cfo.net_worth():>11,.2f}")
        lines.append(f"\n{len(accounts)} account(s)")

        return RouteResult(
            intent="accounts",
            text="\n".join(lines),
            data={"accounts": [a.name for a in accounts], "count": len(accounts)},
        )

    def _spending(self, user_input: str) -> RouteResult:
        # Try to extract a month like "2026-03" or "march"
        month = self._extract_month(user_input)
        month_label = month or datetime.now(timezone.utc).strftime("%Y-%m")

        summary = self._cfo.spending_summary(month_label)
        total = sum(summary.values())

        if not summary:
            return RouteResult(
                intent="spending",
                text=f"No spending data for {month_label}.",
                data={"month": month_label, "total": 0},
            )

        lines = [f"Spending for {month_label}: ${total:,.2f}\n"]
        for cat, amount in sorted(summary.items(), key=lambda x: x[1]):
            label = cat.replace("_", " ").title()
            pct = (amount / total * 100) if total else 0
            lines.append(f"  {label:<25s} ${abs(amount):>10,.2f}  ({pct:4.1f}%)")

        return RouteResult(
            intent="spending",
            text="\n".join(lines),
            data={"month": month_label, "spending": summary, "total": total},
        )

    def _income(self, user_input: str) -> RouteResult:
        month = self._extract_month(user_input)
        month_label = month or datetime.now(timezone.utc).strftime("%Y-%m")

        income = self._cfo.income_summary(month_label)

        return RouteResult(
            intent="income",
            text=f"Income for {month_label}: ${income:,.2f}",
            data={"month": month_label, "income": income},
        )

    def _bills(self, _: str) -> RouteResult:
        overdue = self._cfo.overdue_bills()
        upcoming = self._cfo.upcoming_bills(days=14)

        lines = []
        if overdue:
            lines.append(f"[!!] OVERDUE ({len(overdue)}):")
            for b in overdue:
                lines.append(f"  {b.name}: ${b.amount:.2f} — due {b.due_date}")
            lines.append("")

        if upcoming:
            lines.append(f"Upcoming (next 14 days — {len(upcoming)}):")
            for b in upcoming:
                auto = " (auto-pay)" if b.auto_pay else ""
                lines.append(f"  {b.name}: ${b.amount:.2f} — due {b.due_date}{auto}")
        elif not overdue:
            lines.append("No upcoming or overdue bills.")

        total_bills = len(self._cfo._bills)
        lines.append(f"\nTotal bills tracked: {total_bills}")

        return RouteResult(
            intent="bills",
            text="\n".join(lines),
            data={"overdue": len(overdue), "upcoming": len(upcoming), "total": total_bills},
        )

    def _budget(self, _: str) -> RouteResult:
        checks = self._cfo.budget_check()
        if not checks:
            return RouteResult(
                intent="budget",
                text="No budgets set. Use the CFO agent to set budgets first.",
            )

        lines = [f"{'Category':<25s} {'Budget':>10s} {'Spent':>10s} {'Left':>10s} {'Used':>6s}"]
        lines.append("-" * 65)
        for b in checks:
            status_marker = ""
            if b["status"] == "over":
                status_marker = " [OVER]"
            elif b["status"] == "warning":
                status_marker = " [!]"
            lines.append(
                f"{b['label']:<25s} ${b['limit']:>9,.2f} ${b['spent']:>9,.2f} "
                f"${b['remaining']:>9,.2f} {b['percent_used']:5.1f}%{status_marker}"
            )

        alerts = self._cfo.budget_alerts()
        if alerts:
            lines.append("")
            for a in alerts:
                lines.append(f"  [!] {a}")

        return RouteResult(intent="budget", text="\n".join(lines), data={"checks": checks})

    def _daily_review(self, _: str) -> RouteResult:
        review = self._cfo.daily_review()

        status_icon = {
            "all_clear": "[OK]",
            "review": "[!!]",
            "needs_attention": "[!!]",
        }.get(review["overall_status"], "[??]")

        lines = [
            f"Daily Financial Review — {review['date']}",
            f"{'=' * 50}",
            f"  {status_icon} {review['overall_message']}",
            "",
        ]

        # Transaction check
        tx = review.get("transactions", {})
        if tx:
            lines.append(f"  Transactions: {tx.get('status', 'unknown')} "
                          f"({tx.get('total_checked', 0)} checked, "
                          f"{tx.get('warnings', 0)} warning(s))")

        # Bills
        bills = review.get("bills", {})
        if bills:
            lines.append(f"  Bills: {bills.get('paid', 0)} paid, "
                          f"{bills.get('pending', 0)} pending, "
                          f"{bills.get('overdue', 0)} overdue")

        # Budget
        budget = review.get("budget", {})
        if budget:
            lines.append(f"  Budget: {budget.get('on_track', 0)} on track, "
                          f"{budget.get('warnings', 0)} warning(s), "
                          f"{budget.get('over_budget', 0)} over")

        return RouteResult(intent="daily_review", text="\n".join(lines), data=review)

    def _tax(self, _: str) -> RouteResult:
        recs = self._cfo.tax_recommendations()
        if not recs:
            return RouteResult(
                intent="tax",
                text="No tax recommendations at this time.",
            )

        lines = ["Tax Optimization Recommendations:\n"]
        for i, rec in enumerate(recs, 1):
            lines.append(f"  {i}. {rec}")

        return RouteResult(intent="tax", text="\n".join(lines), data={"recommendations": recs})

    def _home_scenario(self, user_input: str) -> RouteResult:
        # Try to extract price from input
        price_match = re.search(r'\$?([\d,]+(?:\.\d+)?)\s*(?:k|K)?', user_input)
        price = 350_000.0  # default
        if price_match:
            raw = price_match.group(1).replace(",", "")
            parsed = float(raw)
            if parsed < 10_000:
                parsed *= 1000  # "350k" → 350000
            price = parsed

        result = self._cfo.home_purchase_scenario(target_price=price)

        lines = [
            f"Home Purchase Scenario — ${price:,.0f}",
            f"{'=' * 45}",
            f"  Down payment (20%):  ${result['down_payment']:>12,.2f}",
            f"  Loan amount:         ${result['loan_amount']:>12,.2f}",
            f"  Monthly payment:     ${result['monthly_payment']:>12,.2f}",
            f"  Total cost (30yr):   ${result['total_cost']:>12,.2f}",
            f"",
            f"  Current liquid cash: ${result['current_liquid']:>12,.2f}",
        ]
        gap = result["down_payment_gap"]
        if gap > 0:
            lines.append(f"  Down payment gap:    ${gap:>12,.2f}  [need to save more]")
        else:
            lines.append(f"  Down payment gap:    ${'0.00':>12s}  [you're covered!]")

        return RouteResult(intent="home_scenario", text="\n".join(lines), data=result)

    def _trend(self, _: str) -> RouteResult:
        trend = self._cfo.net_worth_trend(months=12)
        if not trend:
            return RouteResult(
                intent="trend",
                text="No net worth history recorded yet. Snapshots are taken during daily sync.",
            )

        lines = ["Net Worth Trend (last 12 months):\n"]
        for point in trend:
            lines.append(f"  {point['date']}  ${point['net_worth']:>12,.2f}")

        first = trend[0]["net_worth"]
        last = trend[-1]["net_worth"]
        change = last - first
        direction = "up" if change >= 0 else "down"
        lines.append(f"\n  Change: ${change:+,.2f} ({direction})")

        return RouteResult(intent="trend", text="\n".join(lines), data={"trend": trend})

    def _sync_status(self, _: str) -> RouteResult:
        plaid = self._cfo.plaid_status()
        rm = self._cfo.rocket_money_status()
        empower = self._cfo.empower_status()

        lines = [
            "Sync Status",
            "-" * 40,
            f"  Plaid:        {'connected' if plaid.get('connected') else 'offline'} "
            f"({plaid.get('connected_institutions', 0)} bank(s))",
            f"  Rocket Money: {'connected' if rm.get('connected') else 'offline'} "
            f"(mode: {rm.get('sync_mode', 'n/a')})",
            f"  Empower:      {'connected' if empower.get('connected') else 'offline'}",
        ]

        last = self._cfo._last_sync
        if last:
            lines.append(f"\n  Last sync: {last}")

        return RouteResult(
            intent="sync_status",
            text="\n".join(lines),
            data={"plaid": plaid, "rocket_money": rm, "empower": empower},
        )

    def _excel(self, _: str) -> RouteResult:
        path = self._cfo.generate_excel()
        return RouteResult(
            intent="excel",
            text=f"Excel dashboard saved to: {path}\nOpen it in Excel, Google Sheets, or LibreOffice.",
            data={"path": str(path)},
        )

    def _validate(self, _: str) -> RouteResult:
        report = self._cfo.validation_report()

        lines = [
            "CFO Validation Report",
            "=" * 50,
            f"  Total Assets:      ${report['total_assets']:>12,.2f}",
            f"  Total Liabilities: ${report['total_liabilities']:>12,.2f}",
            f"  Net Worth:         ${report['net_worth']:>12,.2f}",
            "",
            f"  Accounts: {report['account_count']}",
            f"  Transactions: {report['transaction_count']}",
        ]

        bills = report.get("bills", {})
        overdue = bills.get("overdue", [])
        if overdue:
            lines.append(f"\n  [!!] {len(overdue)} overdue bill(s)")

        recs = report.get("tax_recommendations", [])
        if recs:
            lines.append(f"\n  Tax recommendations ({len(recs)}):")
            for r in recs[:3]:
                lines.append(f"    - {r}")

        return RouteResult(intent="validate", text="\n".join(lines), data=report)

    def _transactions(self, _: str) -> RouteResult:
        txns = sorted(self._cfo._transactions, key=lambda t: t.date, reverse=True)[:20]
        if not txns:
            return RouteResult(
                intent="transactions",
                text="No transactions on record.",
            )

        lines = [f"{'Date':<12s} {'Description':<35s} {'Amount':>10s}"]
        lines.append("-" * 59)
        for tx in txns:
            amt_str = f"${tx.amount:>9,.2f}"
            lines.append(f"{tx.date:<12s} {tx.description[:35]:<35s} {amt_str}")
        lines.append(f"\nShowing {len(txns)} most recent (of {len(self._cfo._transactions)} total)")

        return RouteResult(
            intent="transactions",
            text="\n".join(lines),
            data={"shown": len(txns), "total": len(self._cfo._transactions)},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_month(text: str) -> str | None:
        """Try to pull a YYYY-MM month from user input."""
        m = re.search(r"(\d{4})-(\d{2})", text)
        if m:
            return m.group(0)

        months = {
            "january": "01", "february": "02", "march": "03", "april": "04",
            "may": "05", "june": "06", "july": "07", "august": "08",
            "september": "09", "october": "10", "november": "11", "december": "12",
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "jun": "06", "jul": "07", "aug": "08", "sep": "09",
            "oct": "10", "nov": "11", "dec": "12",
        }
        lower = text.lower()
        for name, num in months.items():
            if name in lower:
                year = datetime.now(timezone.utc).year
                return f"{year}-{num}"

        return None


def run_cfo_repl(cfo: "CFO") -> None:
    """Interactive REPL for conversational CFO commands."""
    router = CFORouter(cfo)

    print()
    print("=" * 55)
    print("  Guardian One — CFO Financial Assistant")
    print("=" * 55)
    print("  Ask me anything about your finances.")
    print("  Type 'help' for available commands, 'exit' to quit.")
    print()

    while True:
        try:
            user_input = input("  CFO > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye.")
            break

        if not user_input:
            continue

        result = router.handle(user_input)

        # Indent all output lines for clean formatting
        for line in result.text.split("\n"):
            print(f"  {line}")
        print()

        if result.data.get("exit"):
            break
