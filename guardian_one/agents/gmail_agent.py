"""Gmail Agent — Email Monitoring & Intelligence.

Responsibilities:
- Monitor Gmail inbox for Jeremy (jeremytabernero@gmail.com)
- Search for specific emails (Rocket Money CSV exports, bills, etc.)
- Track unread messages and important alerts
- Download and process email attachments (CSV exports)
- Coordinate with CFO agent for financial data ingestion
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.base_agent import AgentReport, AgentStatus, BaseAgent
from guardian_one.core.config import AgentConfig
from guardian_one.core.content_gate import redact_dict, redact_text
from guardian_one.integrations.gmail_sync import (
    EmailMessage,
    GmailProvider,
    RocketMoneyCSVChecker,
)


class GmailAgent(BaseAgent):
    """Gmail monitoring agent for Jeremy.

    Monitors jeremytabernero@gmail.com for:
    - Rocket Money CSV transaction exports
    - Bill notifications and payment confirmations
    - Financial alerts from banking institutions
    - Important unread messages
    """

    TARGET_EMAIL = "jeremytabernero@gmail.com"

    def __init__(
        self,
        config: AgentConfig,
        audit: AuditLog,
        credentials_path: str | Path | None = None,
        token_path: str | Path | None = None,
        data_dir: str | Path = "data",
    ) -> None:
        super().__init__(config, audit)
        self._gmail = GmailProvider(
            credentials_path=credentials_path,
            token_path=token_path,
            user_email="me",
        )
        self._csv_checker = RocketMoneyCSVChecker(self._gmail)
        self._data_dir = Path(data_dir)
        self._last_check: dict[str, Any] = {}
        self._inbox_summary: dict[str, Any] = {}
        self._rocket_money_status: dict[str, Any] = {}

    @property
    def gmail(self) -> GmailProvider:
        return self._gmail

    @property
    def csv_checker(self) -> RocketMoneyCSVChecker:
        return self._csv_checker

    def initialize(self) -> None:
        self._set_status(AgentStatus.IDLE)
        authenticated = self._gmail.authenticate()
        self.log("initialized", details={
            "target_email": redact_text(self.TARGET_EMAIL),
            "authenticated": authenticated,
            "has_credentials": self._gmail.has_credentials,
            "has_token": self._gmail.has_token,
        })

    # ------------------------------------------------------------------
    # Inbox monitoring
    # ------------------------------------------------------------------

    def check_inbox(self) -> dict[str, Any]:
        """Check inbox status — unread count and recent important messages."""
        if not self._gmail.is_authenticated:
            return {
                "authenticated": False,
                "error": "Gmail not authenticated. Complete OAuth2 setup first.",
            }

        unread = self._gmail.get_unread_count()
        recent = self._gmail.list_messages(query="is:unread", max_results=10)

        recent_details = []
        for ref in recent[:5]:
            msg = self._gmail.get_message(ref["id"], format="metadata")
            if msg:
                recent_details.append(redact_dict({
                    "subject": msg.subject,
                    "sender": msg.sender,
                    "date": msg.date,
                    "snippet": msg.snippet,
                }))

        self._inbox_summary = {
            "unread_count": unread,
            "recent_unread": recent_details,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        self.log("inbox_checked", details={
            "unread_count": unread,
            "recent_count": len(recent_details),
        })
        return self._inbox_summary

    # ------------------------------------------------------------------
    # Rocket Money CSV detection
    # ------------------------------------------------------------------

    def check_rocket_money_csv(
        self,
        days_back: int | None = 30,
    ) -> dict[str, Any]:
        """Check if Rocket Money has sent a CSV export to Jeremy's Gmail.

        Returns:
            Result dict with 'found', 'count', 'emails', etc.
        """
        result = self._csv_checker.check(
            recipient=self.TARGET_EMAIL,
            days_back=days_back,
        )
        self._rocket_money_status = result

        if result.get("found"):
            self.log("rocket_money_csv_found", details={
                "count": result["count"],
                "latest_date": result["emails"][0]["date"] if result["emails"] else "",
            })
        else:
            self.log("rocket_money_csv_not_found", details={
                "query": result.get("query", ""),
                "error": result.get("error", ""),
            })

        return result

    def download_rocket_money_csv(self) -> dict[str, Any]:
        """Download the latest Rocket Money CSV to the data directory."""
        result = self._csv_checker.download_latest_csv(
            recipient=self.TARGET_EMAIL,
            save_dir=self._data_dir,
        )
        if result.get("success"):
            self.log("rocket_money_csv_downloaded", details={
                "path": result["path"],
                "size": result.get("size", 0),
            })
        else:
            self.log("rocket_money_csv_download_failed",
                     severity=Severity.WARNING,
                     details={"error": result.get("error", "")})
        return result

    # ------------------------------------------------------------------
    # CSV processing (works with locally provided CSV too)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_rocket_money_csv(csv_path: str | Path) -> list[dict[str, str]]:
        """Parse a Rocket Money / Truebill transaction CSV file.

        Returns:
            List of transaction dicts with keys matching CSV headers.
        """
        path = Path(csv_path)
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        return [row for row in reader]

    @staticmethod
    def summarize_csv_transactions(transactions: list[dict[str, str]]) -> dict[str, Any]:
        """Produce a summary of parsed Rocket Money CSV transactions.

        Rocket Money / Truebill CSV columns:
            Date, Original Date, Account Type, Account Name, Account Number,
            Institution Name, Name, Custom Name, Amount, Description,
            Category, Note, Ignored From, Tax Deductible, Transaction Tags

        Amount convention: positive = expense/outflow, negative = income/inflow.
        """
        if not transactions:
            return {"total_transactions": 0}

        total_income = 0.0
        total_expenses = 0.0
        categories: dict[str, float] = {}
        accounts: dict[str, int] = {}
        institutions: set[str] = set()

        for tx in transactions:
            amount_str = tx.get("Amount", tx.get("amount", "0"))
            try:
                amount = float(str(amount_str).replace(",", "").replace("$", ""))
            except (ValueError, AttributeError):
                amount = 0.0

            # Rocket Money: positive = expense, negative = income
            if amount < 0:
                total_income += abs(amount)
            else:
                total_expenses += amount

            cat = tx.get("Category", tx.get("category", "Uncategorized"))
            if cat:
                categories[cat] = categories.get(cat, 0) + abs(amount)

            acct_name = tx.get("Account Name", tx.get("account", ""))
            if acct_name:
                accounts[acct_name] = accounts.get(acct_name, 0) + 1

            inst = tx.get("Institution Name", "")
            if inst:
                institutions.add(inst)

        # Sort categories by total amount
        sorted_cats = dict(sorted(categories.items(), key=lambda x: x[1], reverse=True))

        # Redact account names and institution names that may contain PII
        safe_accounts = {redact_text(k): v for k, v in accounts.items()}
        safe_institutions = sorted(redact_text(inst) for inst in institutions)

        return {
            "total_transactions": len(transactions),
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net": round(total_income - total_expenses, 2),
            "categories": sorted_cats,
            "accounts": safe_accounts,
            "institutions": safe_institutions,
            "date_range": {
                "earliest": min(
                    (tx.get("Date", tx.get("date", "")) for tx in transactions),
                    default="",
                ),
                "latest": max(
                    (tx.get("Date", tx.get("date", "")) for tx in transactions),
                    default="",
                ),
            },
        }

    # ------------------------------------------------------------------
    # Financial email search
    # ------------------------------------------------------------------

    def search_financial_emails(self, days_back: int = 30) -> list[dict[str, Any]]:
        """Search for financial-related emails (bills, payments, banks)."""
        if not self._gmail.is_authenticated:
            return []

        queries = [
            "from:chase.com newer_than:{}d".format(days_back),
            "from:ally.com newer_than:{}d".format(days_back),
            "from:goldmansachs.com newer_than:{}d".format(days_back),
            "from:fidelity.com newer_than:{}d".format(days_back),
            "from:vanguard.com newer_than:{}d".format(days_back),
            "from:rocketmoney.com newer_than:{}d".format(days_back),
            "subject:payment subject:bill newer_than:{}d".format(days_back),
        ]

        results = []
        for q in queries:
            msgs = self._gmail.list_messages(query=q, max_results=5)
            for ref in msgs:
                msg = self._gmail.get_message(ref["id"], format="metadata")
                if msg:
                    results.append(redact_dict({
                        "subject": msg.subject,
                        "sender": msg.sender,
                        "date": msg.date,
                        "snippet": msg.snippet,
                        "labels": msg.labels,
                    }))

        self.log("financial_emails_searched", details={
            "results_count": len(results),
            "days_back": days_back,
        })
        return results

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def run(self) -> AgentReport:
        self._set_status(AgentStatus.RUNNING)
        alerts: list[str] = []
        recommendations: list[str] = []
        actions: list[str] = []

        # Check authentication
        if not self._gmail.is_authenticated:
            alerts.append(
                "Gmail not authenticated. Run OAuth2 setup: "
                "place google_credentials.json in config/ and run interactively."
            )
            recommendations.append(
                "Set up Gmail OAuth2 to enable inbox monitoring and CSV detection."
            )
            actions.append("Authentication check — not yet configured.")
            self._set_status(AgentStatus.IDLE)
            return AgentReport(
                agent_name=self.name,
                status=AgentStatus.IDLE.value,
                summary="Gmail agent awaiting OAuth2 configuration.",
                actions_taken=actions,
                recommendations=recommendations,
                alerts=alerts,
            )

        # Monitor inbox
        inbox = self.check_inbox()
        unread = inbox.get("unread_count", 0)
        if unread > 0:
            actions.append(f"Inbox: {unread} unread messages.")
            if unread > 20:
                alerts.append(f"High unread count: {unread} messages pending.")

        # Check for Rocket Money CSV
        csv_result = self.check_rocket_money_csv(days_back=30)
        if csv_result.get("found"):
            count = csv_result["count"]
            actions.append(f"Found {count} Rocket Money CSV email(s) in the last 30 days.")
            recommendations.append(
                "Rocket Money CSV available — consider downloading for CFO ledger update."
            )
        else:
            actions.append("No Rocket Money CSV emails found in the last 30 days.")
            recommendations.append(
                "Request a Rocket Money CSV export to keep financial data current."
            )

        self._set_status(AgentStatus.IDLE)
        return AgentReport(
            agent_name=self.name,
            status=AgentStatus.IDLE.value,
            summary=f"Gmail: {unread} unread | Rocket Money CSV: {'found' if csv_result.get('found') else 'not found'}",
            actions_taken=actions,
            recommendations=recommendations,
            alerts=alerts,
            data={
                "inbox": self._inbox_summary,
                "rocket_money": self._rocket_money_status,
            },
        )

    def report(self) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            status=self.status.value,
            summary=f"Monitoring {redact_text(self.TARGET_EMAIL)} | Auth: {self._gmail.is_authenticated}",
            data={
                "inbox": self._inbox_summary,
                "rocket_money": self._rocket_money_status,
                "authenticated": self._gmail.is_authenticated,
            },
        )
