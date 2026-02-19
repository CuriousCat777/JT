"""CFO — Financial Management Agent.

Responsibilities:
- Sync with Rocket Money (account unification)
- Dashboard: income, expenses, loans, savings
- Bill alerts and payment confirmations
- Tax optimisation (retirement, charitable giving)
- Scenario planning (home purchase, retirement)
- Encrypted financial records with offline backup support
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig


class AccountType(Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit_card"
    LOAN = "loan"
    INVESTMENT = "investment"
    RETIREMENT = "retirement"


class TransactionCategory(Enum):
    INCOME = "income"
    HOUSING = "housing"
    UTILITIES = "utilities"
    FOOD = "food"
    TRANSPORT = "transport"
    MEDICAL = "medical"
    ENTERTAINMENT = "entertainment"
    EDUCATION = "education"
    INSURANCE = "insurance"
    LOAN_PAYMENT = "loan_payment"
    SAVINGS = "savings"
    CHARITABLE = "charitable"
    OTHER = "other"


@dataclass
class Account:
    name: str
    account_type: AccountType
    balance: float
    institution: str = ""
    last_synced: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class Transaction:
    date: str
    description: str
    amount: float  # Positive = inflow, negative = outflow
    category: TransactionCategory = TransactionCategory.OTHER
    account: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Bill:
    name: str
    amount: float
    due_date: str  # ISO date
    recurring: bool = True
    frequency: str = "monthly"
    auto_pay: bool = False
    paid: bool = False


@dataclass
class Scenario:
    """A financial scenario for planning purposes."""
    name: str
    description: str
    assumptions: dict[str, Any] = field(default_factory=dict)
    projections: dict[str, Any] = field(default_factory=dict)


class CFO(BaseAgent):
    """Financial management agent for Jeremy."""

    def __init__(self, config: AgentConfig, audit: AuditLog) -> None:
        super().__init__(config, audit)
        self._accounts: dict[str, Account] = {}
        self._transactions: list[Transaction] = []
        self._bills: list[Bill] = []
        self._scenarios: dict[str, Scenario] = {}

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        self.log("initialized")

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def add_account(self, account: Account) -> None:
        self._accounts[account.name] = account
        self.log("account_added", details={"name": account.name, "type": account.account_type.value})

    def get_account(self, name: str) -> Account | None:
        return self._accounts.get(name)

    def net_worth(self) -> float:
        return sum(a.balance for a in self._accounts.values())

    def balances_by_type(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for account in self._accounts.values():
            key = account.account_type.value
            totals[key] = totals.get(key, 0) + account.balance
        return totals

    # ------------------------------------------------------------------
    # Transaction tracking
    # ------------------------------------------------------------------

    def record_transaction(self, tx: Transaction) -> None:
        self._transactions.append(tx)

    def spending_summary(self, month: str | None = None) -> dict[str, float]:
        """Summarise spending by category.  month format: 'YYYY-MM'."""
        totals: dict[str, float] = {}
        for tx in self._transactions:
            if month and not tx.date.startswith(month):
                continue
            if tx.amount < 0:  # outflow
                key = tx.category.value
                totals[key] = totals.get(key, 0) + abs(tx.amount)
        return totals

    def income_summary(self, month: str | None = None) -> float:
        return sum(
            tx.amount for tx in self._transactions
            if tx.amount > 0 and (month is None or tx.date.startswith(month))
        )

    # ------------------------------------------------------------------
    # Bill management
    # ------------------------------------------------------------------

    def add_bill(self, bill: Bill) -> None:
        self._bills.append(bill)
        self.log("bill_added", details={"name": bill.name, "due": bill.due_date})

    def upcoming_bills(self, days: int = 7) -> list[Bill]:
        now = datetime.now(timezone.utc)
        cutoff = now.isoformat()[:10]
        from datetime import timedelta
        end = (now + timedelta(days=days)).isoformat()[:10]
        return [
            b for b in self._bills
            if not b.paid and cutoff <= b.due_date <= end
        ]

    def overdue_bills(self) -> list[Bill]:
        today = datetime.now(timezone.utc).isoformat()[:10]
        return [b for b in self._bills if not b.paid and b.due_date < today]

    # ------------------------------------------------------------------
    # Tax optimisation
    # ------------------------------------------------------------------

    def tax_recommendations(self) -> list[str]:
        """Generate tax optimisation recommendations."""
        recs: list[str] = []

        # Retirement contribution check
        retirement = [a for a in self._accounts.values() if a.account_type == AccountType.RETIREMENT]
        if not retirement:
            recs.append("No retirement accounts detected. Consider opening a 401(k) or IRA to reduce taxable income.")
        else:
            total = sum(a.balance for a in retirement)
            recs.append(f"Retirement balance: ${total:,.2f}. Ensure you are maximising annual contribution limits.")

        # Charitable giving
        charitable_spend = sum(
            abs(tx.amount) for tx in self._transactions
            if tx.category == TransactionCategory.CHARITABLE
        )
        if charitable_spend > 0:
            recs.append(f"Charitable giving: ${charitable_spend:,.2f} — ensure receipts are filed for deduction.")
        else:
            recs.append("Consider charitable donations for potential tax deductions.")

        # Student loan interest
        loan_payments = sum(
            abs(tx.amount) for tx in self._transactions
            if tx.category == TransactionCategory.LOAN_PAYMENT
        )
        if loan_payments > 0:
            recs.append(f"Loan payments: ${loan_payments:,.2f}. Student loan interest may be deductible (up to $2,500/year).")

        return recs

    # ------------------------------------------------------------------
    # Scenario planning
    # ------------------------------------------------------------------

    def create_scenario(self, scenario: Scenario) -> None:
        self._scenarios[scenario.name] = scenario
        self.log("scenario_created", details={"name": scenario.name})

    def home_purchase_scenario(
        self,
        target_price: float,
        down_payment_pct: float = 0.20,
        interest_rate: float = 0.065,
        term_years: int = 30,
    ) -> dict[str, Any]:
        """Simple home purchase affordability projection."""
        down = target_price * down_payment_pct
        loan = target_price - down
        monthly_rate = interest_rate / 12
        n_payments = term_years * 12

        if monthly_rate > 0:
            monthly_payment = loan * (monthly_rate * (1 + monthly_rate) ** n_payments) / (
                (1 + monthly_rate) ** n_payments - 1
            )
        else:
            monthly_payment = loan / n_payments

        current_savings = sum(
            a.balance for a in self._accounts.values()
            if a.account_type in (AccountType.SAVINGS, AccountType.CHECKING)
        )

        result = {
            "target_price": target_price,
            "down_payment": round(down, 2),
            "loan_amount": round(loan, 2),
            "monthly_payment": round(monthly_payment, 2),
            "total_cost": round(monthly_payment * n_payments + down, 2),
            "current_liquid": round(current_savings, 2),
            "down_payment_gap": round(max(0, down - current_savings), 2),
        }

        self.create_scenario(Scenario(
            name="home_purchase",
            description=f"${target_price:,.0f} home at {interest_rate*100:.1f}% over {term_years}yr",
            assumptions={"price": target_price, "rate": interest_rate, "term": term_years},
            projections=result,
        ))
        return result

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def dashboard(self) -> dict[str, Any]:
        """Full financial snapshot."""
        return {
            "net_worth": self.net_worth(),
            "balances_by_type": self.balances_by_type(),
            "accounts": len(self._accounts),
            "upcoming_bills": [
                {"name": b.name, "amount": b.amount, "due": b.due_date}
                for b in self.upcoming_bills()
            ],
            "overdue_bills": [
                {"name": b.name, "amount": b.amount, "due": b.due_date}
                for b in self.overdue_bills()
            ],
            "spending_this_month": self.spending_summary(
                datetime.now(timezone.utc).isoformat()[:7]
            ),
            "income_this_month": self.income_summary(
                datetime.now(timezone.utc).isoformat()[:7]
            ),
        }

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        alerts: list[str] = []
        recommendations: list[str] = []
        actions: list[str] = []

        # Bill checks
        overdue = self.overdue_bills()
        if overdue:
            for b in overdue:
                alerts.append(f"OVERDUE: {b.name} — ${b.amount:.2f} was due {b.due_date}")

        upcoming = self.upcoming_bills()
        if upcoming:
            for b in upcoming:
                if not b.auto_pay:
                    alerts.append(f"Bill due soon: {b.name} — ${b.amount:.2f} on {b.due_date}")

        # Tax recs
        tax_recs = self.tax_recommendations()
        recommendations.extend(tax_recs)

        actions.append("Generated financial dashboard and tax recommendations.")
        self._set_status(AgentStatus.IDLE)

        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=f"Net worth: ${self.net_worth():,.2f} | {len(self._accounts)} accounts | {len(overdue)} overdue bills.",
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data=self.dashboard(),
        )

    def report(self) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=f"Tracking {len(self._accounts)} accounts, {len(self._bills)} bills, {len(self._scenarios)} scenarios.",
            data=self.dashboard(),
        )
