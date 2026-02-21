"""CFO Dashboard — Excel spreadsheet generator.

Generates a color-coded, plain-English Excel workbook that anyone
can open and understand.  No financial jargon, no tiny numbers
buried in tables — big, clear sections with colors that tell
you if things are good (green) or need attention (red/yellow).

Sheets:
    1. My Money       — Big-picture snapshot (net worth, what you have, what you owe)
    2. Accounts        — Every account with balance, bank, type
    3. Monthly Spending — Where your money went this month, by category
    4. Transactions    — Every transaction, sortable in Excel
    5. Bills           — What's due, what's overdue, auto-pay status
    6. Trends          — Month-by-month spending and income history

Usage:
    from guardian_one.agents.cfo_dashboard import generate_dashboard
    generate_dashboard(cfo, "data/dashboard.xlsx")
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side, numbers
from openpyxl.utils import get_column_letter

if TYPE_CHECKING:
    from guardian_one.agents.cfo import CFO


# -----------------------------------------------------------------------
# Color palette — simple, high-contrast
# -----------------------------------------------------------------------
_GREEN = PatternFill(start_color="22C55E", end_color="22C55E", fill_type="solid")
_LIGHT_GREEN = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
_RED = PatternFill(start_color="EF4444", end_color="EF4444", fill_type="solid")
_LIGHT_RED = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
_YELLOW = PatternFill(start_color="F59E0B", end_color="F59E0B", fill_type="solid")
_LIGHT_YELLOW = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
_BLUE = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
_LIGHT_BLUE = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
_DARK = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
_HEADER_BG = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
_STRIPE = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
_WHITE = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

_TITLE_FONT = Font(name="Calibri", size=20, bold=True, color="1E293B")
_SUBTITLE_FONT = Font(name="Calibri", size=13, color="64748B")
_BIG_NUMBER = Font(name="Calibri", size=28, bold=True, color="1E293B")
_BIG_GREEN = Font(name="Calibri", size=28, bold=True, color="16A34A")
_BIG_RED = Font(name="Calibri", size=28, bold=True, color="DC2626")
_HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_BODY_FONT = Font(name="Calibri", size=11, color="334155")
_BODY_BOLD = Font(name="Calibri", size=11, bold=True, color="334155")
_LABEL_FONT = Font(name="Calibri", size=12, color="64748B")
_SECTION_FONT = Font(name="Calibri", size=14, bold=True, color="1E293B")
_MONEY_FORMAT = '#,##0.00_);[Red](#,##0.00)'
_MONEY_FORMAT_POS = '[Green]#,##0.00_);[Red](#,##0.00)'

_THIN_BORDER = Border(
    bottom=Side(style="thin", color="E2E8F0"),
)
_HEADER_BORDER = Border(
    bottom=Side(style="medium", color="94A3B8"),
)

# Friendly names for account types
_ACCOUNT_TYPE_LABELS = {
    "checking": "Checking",
    "savings": "Savings",
    "credit_card": "Credit Card",
    "loan": "Loan",
    "investment": "Investments",
    "retirement": "Retirement",
}

# Friendly names for spending categories
_CATEGORY_LABELS = {
    "income": "Income",
    "housing": "Housing / Rent",
    "utilities": "Utilities",
    "food": "Food & Groceries",
    "transport": "Transportation",
    "medical": "Medical / Health",
    "entertainment": "Shopping & Fun",
    "education": "Education",
    "insurance": "Insurance",
    "loan_payment": "Loan Payments",
    "savings": "Savings / Transfers",
    "charitable": "Donations",
    "other": "Other",
}


def generate_dashboard(
    cfo: "CFO",
    output_path: str | Path = "data/dashboard.xlsx",
    password: str | None = None,
    gmail_data: dict[str, Any] | None = None,
) -> Path:
    """Generate the full Excel dashboard from current CFO data.

    Args:
        cfo: The CFO agent instance
        output_path: Where to save the .xlsx file
        password: Optional password to protect the workbook.
                  When set, every sheet is locked — data is visible
                  but cells cannot be edited without the password.
        gmail_data: Optional Gmail financial email data for the daily check sheet.

    Returns the path to the generated file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    # Remove default sheet
    wb.remove(wb.active)

    _build_daily_check_sheet(wb, cfo, gmail_data)
    _build_my_money_sheet(wb, cfo)
    _build_accounts_sheet(wb, cfo)
    _build_spending_sheet(wb, cfo)
    _build_budget_sheet(wb, cfo)
    _build_transactions_sheet(wb, cfo)
    _build_bills_sheet(wb, cfo)
    _build_trends_sheet(wb, cfo)

    # Password-protect every sheet (read-only unless you know the password)
    if password:
        for ws in wb.worksheets:
            ws.protection.sheet = True
            ws.protection.password = password
            ws.protection.enable()
        # Also protect the workbook structure (can't add/delete/rename sheets)
        wb.security.workbookPassword = password
        wb.security.lockStructure = True

    wb.save(str(output_path))
    return output_path


# -----------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------

def _set_col_widths(ws: Any, widths: dict[str, float]) -> None:
    for col_letter, w in widths.items():
        ws.column_dimensions[col_letter].width = w


def _write_header_row(ws: Any, row: int, headers: list[str], start_col: int = 1) -> None:
    for i, h in enumerate(headers):
        cell = ws.cell(row=row, column=start_col + i, value=h)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_BG
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _HEADER_BORDER


def _write_data_row(ws: Any, row: int, values: list[Any], start_col: int = 1, stripe: bool = False) -> None:
    for i, v in enumerate(values):
        cell = ws.cell(row=row, column=start_col + i, value=v)
        cell.font = _BODY_FONT
        cell.border = _THIN_BORDER
        if stripe:
            cell.fill = _STRIPE
        # Format money columns
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            cell.number_format = _MONEY_FORMAT
            cell.alignment = Alignment(horizontal="right")


def _write_big_stat(ws: Any, row: int, col: int, label: str, value: float, fmt: str = "money") -> None:
    """Write a big stat block: label on top, large number below."""
    label_cell = ws.cell(row=row, column=col, value=label)
    label_cell.font = _LABEL_FONT
    label_cell.alignment = Alignment(horizontal="center")

    val_cell = ws.cell(row=row + 1, column=col, value=value)
    if fmt == "money":
        val_cell.number_format = _MONEY_FORMAT
        if value >= 0:
            val_cell.font = _BIG_GREEN
        else:
            val_cell.font = _BIG_RED
    else:
        val_cell.font = _BIG_NUMBER
    val_cell.alignment = Alignment(horizontal="center")


# -----------------------------------------------------------------------
# Sheet 0: Daily Check (first sheet you see when you open the file)
# -----------------------------------------------------------------------

def _build_daily_check_sheet(wb: Workbook, cfo: "CFO", gmail_data: dict[str, Any] | None = None) -> None:
    ws = wb.create_sheet("Daily Check")
    ws.sheet_properties.tabColor = "F97316"  # Orange — attention

    _set_col_widths(ws, {"A": 4, "B": 45, "C": 18, "D": 22, "E": 4})

    # Run the daily review
    review = cfo.daily_review(gmail_data)

    # Title with status color
    ws.merge_cells("B2:D2")
    ws.cell(row=2, column=2, value="Daily Financial Check").font = _TITLE_FONT

    now_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    ws.cell(row=3, column=2, value=now_str).font = _SUBTITLE_FONT

    # Overall status banner
    status = review["overall_status"]
    status_labels = {
        "all_clear": "ALL CLEAR — Everything looks good",
        "review": "A FEW THINGS TO LOOK AT",
        "needs_attention": "NEEDS YOUR ATTENTION",
    }
    status_fills = {
        "all_clear": _GREEN,
        "review": _YELLOW,
        "needs_attention": _RED,
    }

    ws.merge_cells("B5:D5")
    status_cell = ws.cell(row=5, column=2, value=status_labels.get(status, status))
    status_cell.font = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
    status_cell.fill = status_fills.get(status, _YELLOW)
    status_cell.alignment = Alignment(horizontal="center", vertical="center")
    for col in [3, 4]:
        ws.cell(row=5, column=col).fill = status_fills.get(status, _YELLOW)
    ws.row_dimensions[5].height = 40

    ws.merge_cells("B6:D6")
    ws.cell(row=6, column=2, value=review["overall_message"]).font = Font(
        name="Calibri", size=12, color="475569")
    ws.cell(row=6, column=2).alignment = Alignment(horizontal="center")

    row = 8

    # --- Section 1: Transaction Verification ---
    ws.merge_cells(f"B{row}:D{row}")
    ws.cell(row=row, column=2, value="Transaction Check").font = _SECTION_FONT
    row += 1

    tx = review["transactions"]
    ws.cell(row=row, column=2, value=f"Checked {tx['checked']} transactions from the last {tx.get('days', 7)} days").font = _BODY_FONT
    ws.cell(row=row, column=3, value=tx["summary"]).font = _BODY_BOLD
    row += 1

    if tx["issues"]:
        _write_header_row(ws, row, ["Issue", "Severity", "Details"], start_col=2)
        row += 1
        for issue in tx["issues"]:
            sev = issue["severity"].upper()
            _write_data_row(ws, row, [issue["description"], sev, ""], start_col=2,
                            stripe=(row % 2 == 0))
            if issue["severity"] == "warning":
                for c in range(2, 5):
                    ws.cell(row=row, column=c).fill = _LIGHT_RED
            else:
                for c in range(2, 5):
                    ws.cell(row=row, column=c).fill = _LIGHT_YELLOW
            row += 1
    else:
        ws.cell(row=row, column=2, value="No issues found.").font = _BODY_FONT
        ws.cell(row=row, column=2).fill = _LIGHT_GREEN
        ws.cell(row=row, column=3).fill = _LIGHT_GREEN
        ws.cell(row=row, column=4).fill = _LIGHT_GREEN
        row += 1

    row += 1

    # --- Section 2: Bill Verification ---
    ws.merge_cells(f"B{row}:D{row}")
    ws.cell(row=row, column=2, value="Bill Payment Verification").font = _SECTION_FONT
    row += 1

    bills = review["bills"]
    if bills["results"]:
        _write_header_row(ws, row, ["Bill", "Status", "Details"], start_col=2)
        row += 1
        for b in bills["results"]:
            status_display = {
                "confirmed_paid": "Paid",
                "likely_paid": "Likely Paid",
                "pending": "Not Yet Due",
                "overdue_unverified": "OVERDUE!",
            }.get(b["status"], b["status"])

            _write_data_row(ws, row, [b["bill"], status_display, b["message"]], start_col=2,
                            stripe=(row % 2 == 0))

            if b["status"] == "overdue_unverified":
                for c in range(2, 5):
                    ws.cell(row=row, column=c).fill = _LIGHT_RED
                ws.cell(row=row, column=3).font = Font(name="Calibri", size=11, bold=True, color="DC2626")
            elif b["status"] in ("confirmed_paid", "likely_paid"):
                ws.cell(row=row, column=3).font = Font(name="Calibri", size=11, color="16A34A")
                ws.cell(row=row, column=3).fill = _LIGHT_GREEN
            elif b["status"] == "pending":
                ws.cell(row=row, column=3).fill = _LIGHT_YELLOW
            row += 1
    else:
        ws.cell(row=row, column=2, value="No bills tracked.").font = _BODY_FONT
        row += 1

    row += 1

    # --- Section 3: Budget Status ---
    ws.merge_cells(f"B{row}:D{row}")
    ws.cell(row=row, column=2, value="Budget Status").font = _SECTION_FONT
    row += 1

    budget = review["budget"]
    if budget["results"]:
        over = budget["over_budget"]
        warn = budget["warnings"]
        ok = budget["on_track"]

        msg_parts = []
        if ok:
            msg_parts.append(f"{ok} on track")
        if warn:
            msg_parts.append(f"{warn} getting close")
        if over:
            msg_parts.append(f"{over} OVER budget")
        ws.cell(row=row, column=2, value=" | ".join(msg_parts)).font = _BODY_FONT
        row += 1

        for b in budget["results"]:
            label = f"{b['label']}: ${b['spent']:,.0f} of ${b['limit']:,.0f} ({b['percent_used']:.0f}%)"
            ws.cell(row=row, column=2, value=label).font = _BODY_FONT

            if b["status"] == "over":
                ws.cell(row=row, column=2).fill = _LIGHT_RED
                ws.cell(row=row, column=3, value="OVER").font = Font(
                    name="Calibri", size=11, bold=True, color="DC2626")
                ws.cell(row=row, column=3).fill = _LIGHT_RED
            elif b["status"] == "warning":
                ws.cell(row=row, column=2).fill = _LIGHT_YELLOW
                ws.cell(row=row, column=3, value="Close").font = Font(
                    name="Calibri", size=11, bold=True, color="92400E")
                ws.cell(row=row, column=3).fill = _LIGHT_YELLOW
            else:
                ws.cell(row=row, column=3, value="OK").font = Font(
                    name="Calibri", size=11, bold=True, color="16A34A")
                ws.cell(row=row, column=3).fill = _LIGHT_GREEN
            row += 1
    else:
        ws.cell(row=row, column=2, value="No budgets set. Use cfo.set_budget('food', 500) to start.").font = _BODY_FONT
        row += 1

    row += 1

    # --- Section 4: Financial Email Summary ---
    ws.merge_cells(f"B{row}:D{row}")
    ws.cell(row=row, column=2, value="Financial Emails").font = _SECTION_FONT
    row += 1

    emails = review.get("emails", {})
    if emails.get("available") is False:
        ws.cell(row=row, column=2, value="Run 'python main.py --gmail' to include email review.").font = _SUBTITLE_FONT
    elif emails.get("financial_emails"):
        for email in emails["financial_emails"][:10]:
            subj = email.get("subject", "")
            sender = email.get("sender", "")
            date = email.get("date", "")
            ws.cell(row=row, column=2, value=subj).font = _BODY_FONT
            ws.cell(row=row, column=3, value=sender).font = Font(name="Calibri", size=10, color="64748B")
            ws.cell(row=row, column=4, value=date).font = Font(name="Calibri", size=10, color="64748B")
            row += 1
    elif emails.get("inbox"):
        inbox = emails["inbox"]
        ws.cell(row=row, column=2,
                value=f"Inbox: {inbox.get('unread_count', 0)} unread emails").font = _BODY_FONT
        row += 1
    else:
        ws.cell(row=row, column=2, value="No financial emails to report.").font = _BODY_FONT


# -----------------------------------------------------------------------
# Sheet 1: My Money (the big picture)
# -----------------------------------------------------------------------

def _build_my_money_sheet(wb: Workbook, cfo: "CFO") -> None:
    ws = wb.create_sheet("My Money")
    ws.sheet_properties.tabColor = "22C55E"

    _set_col_widths(ws, {"A": 4, "B": 28, "C": 28, "D": 28, "E": 28, "F": 4})

    # Title
    ws.merge_cells("B2:E2")
    title = ws.cell(row=2, column=2, value="My Money")
    title.font = _TITLE_FONT

    now_str = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p")
    ws.merge_cells("B3:E3")
    subtitle = ws.cell(row=3, column=2, value=f"Last updated: {now_str}")
    subtitle.font = _SUBTITLE_FONT

    # Big numbers row
    net = cfo.net_worth()
    by_type = cfo.balances_by_type()

    money_in_bank = sum(v for k, v in by_type.items() if k in ("checking", "savings"))
    money_invested = sum(v for k, v in by_type.items() if k in ("investment", "retirement"))
    money_owed = sum(v for k, v in by_type.items() if k in ("credit_card", "loan"))

    # Row 5-6: Net Worth
    _write_big_stat(ws, 5, 2, "TOTAL NET WORTH", net)

    # Row 5-6: Money in bank
    _write_big_stat(ws, 5, 3, "CASH IN BANK", money_in_bank)

    # Row 5-6: Investments
    _write_big_stat(ws, 5, 4, "INVESTED", money_invested)

    # Row 5-6: What you owe
    _write_big_stat(ws, 5, 5, "WHAT YOU OWE", money_owed)

    # Color blocks behind the numbers
    for col in [2, 3, 4, 5]:
        for r in [5, 6]:
            cell = ws.cell(row=r, column=col)
            if col == 2:
                cell.fill = _LIGHT_BLUE
            elif col in (3, 4):
                cell.fill = _LIGHT_GREEN
            else:
                cell.fill = _LIGHT_RED if money_owed < 0 else _LIGHT_GREEN

    ws.row_dimensions[6].height = 45

    # --- Where your money is (account type breakdown) ---
    row = 9
    ws.merge_cells(f"B{row}:C{row}")
    ws.cell(row=row, column=2, value="Where Your Money Is").font = _SECTION_FONT

    row = 10
    _write_header_row(ws, row, ["Account Type", "Total Balance"], start_col=2)

    row = 11
    for acct_type, balance in sorted(by_type.items(), key=lambda x: -abs(x[1])):
        label = _ACCOUNT_TYPE_LABELS.get(acct_type, acct_type.replace("_", " ").title())
        _write_data_row(ws, row, [label, balance], start_col=2, stripe=(row % 2 == 0))
        # Color the balance
        cell = ws.cell(row=row, column=3)
        if balance >= 0:
            cell.font = Font(name="Calibri", size=11, bold=True, color="16A34A")
        else:
            cell.font = Font(name="Calibri", size=11, bold=True, color="DC2626")
        row += 1

    # Total row
    ws.cell(row=row, column=2, value="NET WORTH").font = _BODY_BOLD
    total_cell = ws.cell(row=row, column=3, value=net)
    total_cell.number_format = _MONEY_FORMAT
    total_cell.font = Font(name="Calibri", size=12, bold=True, color="1E293B")
    total_cell.border = Border(top=Side(style="double", color="334155"))

    # --- This Month spending summary ---
    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    spending = cfo.spending_summary(this_month)
    income = cfo.income_summary(this_month)
    total_spent = sum(spending.values())

    spend_start_row = 9
    ws.merge_cells(f"D{spend_start_row}:E{spend_start_row}")
    month_label = datetime.now(timezone.utc).strftime("%B %Y")
    ws.cell(row=spend_start_row, column=4, value=f"This Month ({month_label})").font = _SECTION_FONT

    _write_header_row(ws, spend_start_row + 1, ["", "Amount"], start_col=4)

    r = spend_start_row + 2
    ws.cell(row=r, column=4, value="Money In (Income)").font = _BODY_FONT
    in_cell = ws.cell(row=r, column=5, value=income)
    in_cell.number_format = _MONEY_FORMAT
    in_cell.font = Font(name="Calibri", size=11, bold=True, color="16A34A")
    in_cell.fill = _LIGHT_GREEN
    ws.cell(row=r, column=4).fill = _LIGHT_GREEN

    r += 1
    ws.cell(row=r, column=4, value="Money Out (Spending)").font = _BODY_FONT
    out_cell = ws.cell(row=r, column=5, value=-total_spent if total_spent else 0)
    out_cell.number_format = _MONEY_FORMAT
    out_cell.font = Font(name="Calibri", size=11, bold=True, color="DC2626")
    out_cell.fill = _LIGHT_RED
    ws.cell(row=r, column=4).fill = _LIGHT_RED

    r += 1
    difference = income - total_spent
    ws.cell(row=r, column=4, value="Left Over").font = _BODY_BOLD
    left_cell = ws.cell(row=r, column=5, value=difference)
    left_cell.number_format = _MONEY_FORMAT
    left_cell.border = Border(top=Side(style="double", color="334155"))
    if difference >= 0:
        left_cell.font = Font(name="Calibri", size=12, bold=True, color="16A34A")
        left_cell.fill = _LIGHT_GREEN
        ws.cell(row=r, column=4).fill = _LIGHT_GREEN
    else:
        left_cell.font = Font(name="Calibri", size=12, bold=True, color="DC2626")
        left_cell.fill = _LIGHT_RED
        ws.cell(row=r, column=4).fill = _LIGHT_RED

    # --- Bills alert ---
    overdue = cfo.overdue_bills()
    upcoming = cfo.upcoming_bills(days=14)

    bills_row = r + 3
    ws.merge_cells(f"D{bills_row}:E{bills_row}")
    ws.cell(row=bills_row, column=4, value="Bills").font = _SECTION_FONT

    bills_row += 1
    if overdue:
        for b in overdue:
            ws.cell(row=bills_row, column=4, value=f"OVERDUE: {b.name}").font = Font(
                name="Calibri", size=11, bold=True, color="FFFFFF")
            ws.cell(row=bills_row, column=4).fill = _RED
            amt = ws.cell(row=bills_row, column=5, value=b.amount)
            amt.number_format = _MONEY_FORMAT
            amt.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            amt.fill = _RED
            bills_row += 1

    if upcoming:
        for b in upcoming:
            auto = " (auto-pay)" if b.auto_pay else ""
            ws.cell(row=bills_row, column=4, value=f"Due {b.due_date}: {b.name}{auto}").font = _BODY_FONT
            ws.cell(row=bills_row, column=4).fill = _LIGHT_YELLOW
            amt = ws.cell(row=bills_row, column=5, value=b.amount)
            amt.number_format = _MONEY_FORMAT
            amt.fill = _LIGHT_YELLOW
            bills_row += 1

    if not overdue and not upcoming:
        ws.cell(row=bills_row, column=4, value="No bills due soon").font = _BODY_FONT
        ws.cell(row=bills_row, column=4).fill = _LIGHT_GREEN
        ws.cell(row=bills_row, column=5).fill = _LIGHT_GREEN

    # --- Data sources status ---
    source_row = bills_row + 2
    ws.merge_cells(f"D{source_row}:E{source_row}")
    ws.cell(row=source_row, column=4, value="Data Sources").font = _SECTION_FONT
    source_row += 1

    sources = [
        ("Plaid (Banks)", cfo._plaid_connected, f"{len(cfo._plaid.connected_institutions)} bank(s)"),
        ("Rocket Money", cfo._rm_connected, "CSV" if not cfo._rm_connected else "API"),
        ("Empower", cfo._empower_connected, "Retirement"),
    ]
    for name, connected, detail in sources:
        status_label = "Connected" if connected else "Offline"
        ws.cell(row=source_row, column=4, value=f"{name}: {status_label}").font = _BODY_FONT
        ws.cell(row=source_row, column=5, value=detail).font = _BODY_FONT
        if connected:
            ws.cell(row=source_row, column=4).fill = _LIGHT_GREEN
            ws.cell(row=source_row, column=5).fill = _LIGHT_GREEN
        else:
            ws.cell(row=source_row, column=4).fill = _LIGHT_YELLOW
            ws.cell(row=source_row, column=5).fill = _LIGHT_YELLOW
        source_row += 1


# -----------------------------------------------------------------------
# Sheet 2: Accounts
# -----------------------------------------------------------------------

def _build_accounts_sheet(wb: Workbook, cfo: "CFO") -> None:
    ws = wb.create_sheet("Accounts")
    ws.sheet_properties.tabColor = "3B82F6"

    _set_col_widths(ws, {"A": 4, "B": 40, "C": 18, "D": 18, "E": 22, "F": 22})

    ws.merge_cells("B2:F2")
    ws.cell(row=2, column=2, value="All Your Accounts").font = _TITLE_FONT
    ws.cell(row=3, column=2, value="Every account we're tracking, sorted by balance").font = _SUBTITLE_FONT

    _write_header_row(ws, 5, ["Account Name", "Type", "Balance", "Bank", "Last Updated"], start_col=2)

    accounts = sorted(cfo._accounts.values(), key=lambda a: -a.balance)
    row = 6
    for a in accounts:
        type_label = _ACCOUNT_TYPE_LABELS.get(a.account_type.value, a.account_type.value)
        last_sync = a.last_synced[:10] if a.last_synced else ""
        _write_data_row(ws, row, [a.name, type_label, a.balance, a.institution, last_sync],
                        start_col=2, stripe=(row % 2 == 0))

        # Color the balance
        bal_cell = ws.cell(row=row, column=4)
        if a.balance >= 0:
            bal_cell.font = Font(name="Calibri", size=11, bold=True, color="16A34A")
        else:
            bal_cell.font = Font(name="Calibri", size=11, bold=True, color="DC2626")
            bal_cell.fill = _LIGHT_RED

        # Color the type
        type_cell = ws.cell(row=row, column=3)
        type_colors = {
            "checking": _LIGHT_BLUE, "savings": _LIGHT_GREEN,
            "credit_card": _LIGHT_RED, "loan": _LIGHT_RED,
            "investment": _LIGHT_BLUE, "retirement": _LIGHT_GREEN,
        }
        type_cell.fill = type_colors.get(a.account_type.value, _WHITE)

        row += 1

    # Total row
    ws.cell(row=row + 1, column=2, value="TOTAL (Net Worth)").font = Font(
        name="Calibri", size=12, bold=True, color="1E293B")
    total = ws.cell(row=row + 1, column=4, value=cfo.net_worth())
    total.number_format = _MONEY_FORMAT
    total.font = Font(name="Calibri", size=13, bold=True, color="1E293B")
    total.border = Border(top=Side(style="double", color="334155"))

    # Add Excel SUM formula too (for users who edit)
    if len(accounts) > 0:
        formula_cell = ws.cell(row=row + 2, column=4)
        formula_cell.value = f"=SUM(D6:D{row - 1})"
        formula_cell.number_format = _MONEY_FORMAT
        formula_cell.font = Font(name="Calibri", size=10, color="94A3B8", italic=True)

    # Auto-filter for sorting
    if len(accounts) > 0:
        ws.auto_filter.ref = f"B5:F{row - 1}"


# -----------------------------------------------------------------------
# Sheet 3: Monthly Spending
# -----------------------------------------------------------------------

def _build_spending_sheet(wb: Workbook, cfo: "CFO") -> None:
    ws = wb.create_sheet("Monthly Spending")
    ws.sheet_properties.tabColor = "EF4444"

    _set_col_widths(ws, {"A": 4, "B": 28, "C": 18, "D": 18, "E": 4, "F": 28, "G": 18})

    this_month = datetime.now(timezone.utc).strftime("%Y-%m")
    month_label = datetime.now(timezone.utc).strftime("%B %Y")

    ws.merge_cells("B2:D2")
    ws.cell(row=2, column=2, value=f"Where Your Money Went — {month_label}").font = _TITLE_FONT
    ws.cell(row=3, column=2, value="Spending broken down by category").font = _SUBTITLE_FONT

    spending = cfo.spending_summary(this_month)
    total_spent = sum(spending.values())
    income = cfo.income_summary(this_month)

    # Big numbers
    _write_big_stat(ws, 5, 2, "TOTAL SPENT", -total_spent if total_spent else 0)
    _write_big_stat(ws, 5, 3, "TOTAL INCOME", income)
    diff = income - total_spent
    _write_big_stat(ws, 5, 4, "LEFT OVER", diff)

    for col in [2, 3, 4]:
        for r in [5, 6]:
            cell = ws.cell(row=r, column=col)
            if col == 2:
                cell.fill = _LIGHT_RED
            elif col == 3:
                cell.fill = _LIGHT_GREEN
            else:
                cell.fill = _LIGHT_GREEN if diff >= 0 else _LIGHT_RED

    ws.row_dimensions[6].height = 45

    # Category table
    _write_header_row(ws, 8, ["Category", "Amount", "% of Total"], start_col=2)

    row = 9
    sorted_spending = sorted(spending.items(), key=lambda x: -x[1])
    for cat, amount in sorted_spending:
        label = _CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
        pct = (amount / total_spent * 100) if total_spent > 0 else 0
        _write_data_row(ws, row, [label, amount, None], start_col=2, stripe=(row % 2 == 0))

        pct_cell = ws.cell(row=row, column=4, value=pct / 100)
        pct_cell.number_format = '0.0%'
        pct_cell.font = _BODY_FONT
        pct_cell.alignment = Alignment(horizontal="right")

        # Color biggest categories
        if pct >= 25:
            ws.cell(row=row, column=2).fill = _LIGHT_RED
            ws.cell(row=row, column=3).fill = _LIGHT_RED
            ws.cell(row=row, column=4).fill = _LIGHT_RED
        elif pct >= 15:
            ws.cell(row=row, column=2).fill = _LIGHT_YELLOW
            ws.cell(row=row, column=3).fill = _LIGHT_YELLOW
            ws.cell(row=row, column=4).fill = _LIGHT_YELLOW

        row += 1

    # Total row
    ws.cell(row=row, column=2, value="TOTAL").font = _BODY_BOLD
    t = ws.cell(row=row, column=3, value=total_spent)
    t.number_format = _MONEY_FORMAT
    t.font = Font(name="Calibri", size=11, bold=True, color="1E293B")
    t.border = Border(top=Side(style="double", color="334155"))

    # Pie chart
    if sorted_spending and len(sorted_spending) > 0:
        chart = PieChart()
        chart.title = f"Spending Breakdown — {month_label}"
        chart.style = 10
        chart.width = 18
        chart.height = 14

        data = Reference(ws, min_col=3, min_row=8, max_row=row - 1)
        cats = Reference(ws, min_col=2, min_row=9, max_row=row - 1)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(cats)
        from openpyxl.chart.label import DataLabelList
        chart.dataLabels = DataLabelList()
        chart.dataLabels.showPercent = True
        chart.dataLabels.showVal = False

        ws.add_chart(chart, "F8")


# -----------------------------------------------------------------------
# Sheet 3b: Budget (Am I on track?)
# -----------------------------------------------------------------------

def _build_budget_sheet(wb: Workbook, cfo: "CFO") -> None:
    ws = wb.create_sheet("Budget")
    ws.sheet_properties.tabColor = "8B5CF6"

    _set_col_widths(ws, {
        "A": 4, "B": 24, "C": 16, "D": 16, "E": 16, "F": 14, "G": 20,
    })

    month_label = datetime.now(timezone.utc).strftime("%B %Y")
    ws.merge_cells("B2:G2")
    ws.cell(row=2, column=2, value=f"Budget Tracker — {month_label}").font = _TITLE_FONT
    ws.cell(row=3, column=2, value="Are you spending more than you planned?").font = _SUBTITLE_FONT

    budget_check = cfo.budget_check()

    if not budget_check:
        ws.cell(row=5, column=2, value="No budgets set yet.").font = _BODY_FONT
        ws.cell(row=6, column=2,
                value="Set budgets with: cfo.set_budget('food', 500)").font = _SUBTITLE_FONT
        ws.cell(row=7, column=2,
                value="Categories: food, housing, utilities, transport, entertainment, medical, education, other").font = _SUBTITLE_FONT
        return

    _write_header_row(ws, 5, ["Category", "Budget", "Spent", "Left", "% Used", "Status"], start_col=2)

    row = 6
    for r in budget_check:
        status_text = {
            "ok": "On Track",
            "warning": "Getting Close",
            "over": "OVER BUDGET",
        }.get(r["status"], r["status"])

        _write_data_row(ws, row, [
            r["label"], r["limit"], r["spent"], r["remaining"], None, status_text,
        ], start_col=2, stripe=(row % 2 == 0))

        # Percentage cell with bar-like formatting
        pct_cell = ws.cell(row=row, column=6, value=r["percent_used"] / 100)
        pct_cell.number_format = '0%'
        pct_cell.font = _BODY_FONT
        pct_cell.alignment = Alignment(horizontal="right")

        # Color the entire row based on status
        if r["status"] == "over":
            for c in range(2, 8):
                ws.cell(row=row, column=c).fill = _LIGHT_RED
            ws.cell(row=row, column=7).font = Font(name="Calibri", size=11, bold=True, color="DC2626")
        elif r["status"] == "warning":
            for c in range(2, 8):
                ws.cell(row=row, column=c).fill = _LIGHT_YELLOW
            ws.cell(row=row, column=7).font = Font(name="Calibri", size=11, bold=True, color="92400E")
        else:
            ws.cell(row=row, column=7).font = Font(name="Calibri", size=11, bold=True, color="16A34A")
            ws.cell(row=row, column=7).fill = _LIGHT_GREEN

        # Color "Left" column
        left_cell = ws.cell(row=row, column=5)
        if r["remaining"] >= 0:
            left_cell.font = Font(name="Calibri", size=11, color="16A34A")
        else:
            left_cell.font = Font(name="Calibri", size=11, bold=True, color="DC2626")

        row += 1

    # Totals
    total_budget = sum(r["limit"] for r in budget_check)
    total_spent = sum(r["spent"] for r in budget_check)
    total_left = total_budget - total_spent

    row += 1
    ws.cell(row=row, column=2, value="TOTAL").font = _BODY_BOLD
    for col, val in [(3, total_budget), (4, total_spent), (5, total_left)]:
        cell = ws.cell(row=row, column=col, value=val)
        cell.number_format = _MONEY_FORMAT
        cell.font = Font(name="Calibri", size=11, bold=True, color="1E293B")
        cell.border = Border(top=Side(style="double", color="334155"))

    # Bar chart — Budget vs Spent per category
    if len(budget_check) > 1:
        chart = BarChart()
        chart.type = "col"
        chart.title = "Budget vs Actual Spending"
        chart.style = 10
        chart.width = 20
        chart.height = 12

        budget_data = Reference(ws, min_col=3, min_row=5, max_row=row - 2)
        spent_data = Reference(ws, min_col=4, min_row=5, max_row=row - 2)
        cats = Reference(ws, min_col=2, min_row=6, max_row=row - 2)

        chart.add_data(budget_data, titles_from_data=True)
        chart.add_data(spent_data, titles_from_data=True)
        chart.set_categories(cats)

        chart.series[0].graphicalProperties.solidFill = "93C5FD"  # Light blue = budget
        chart.series[1].graphicalProperties.solidFill = "EF4444"  # Red = spent

        ws.add_chart(chart, f"B{row + 2}")


# -----------------------------------------------------------------------
# Sheet 4: Transactions
# -----------------------------------------------------------------------

def _build_transactions_sheet(wb: Workbook, cfo: "CFO") -> None:
    ws = wb.create_sheet("Transactions")
    ws.sheet_properties.tabColor = "F59E0B"

    _set_col_widths(ws, {"A": 4, "B": 14, "C": 40, "D": 16, "E": 20, "F": 22})

    ws.merge_cells("B2:F2")
    ws.cell(row=2, column=2, value="All Transactions").font = _TITLE_FONT
    count = len(cfo._transactions)
    ws.cell(row=3, column=2, value=f"{count} transactions — use Excel filters to sort and search").font = _SUBTITLE_FONT

    _write_header_row(ws, 5, ["Date", "Description", "Amount", "Category", "Account"], start_col=2)

    # Sort by date descending (newest first)
    txns = sorted(cfo._transactions, key=lambda t: t.date, reverse=True)
    row = 6
    for tx in txns:
        cat_label = _CATEGORY_LABELS.get(tx.category.value, tx.category.value)
        _write_data_row(ws, row, [tx.date, tx.description, tx.amount, cat_label, tx.account],
                        start_col=2, stripe=(row % 2 == 0))

        # Color amounts: green for income, red for spending
        amt_cell = ws.cell(row=row, column=4)
        if tx.amount >= 0:
            amt_cell.font = Font(name="Calibri", size=11, color="16A34A")
        else:
            amt_cell.font = Font(name="Calibri", size=11, color="DC2626")

        row += 1

    # Auto-filter for sorting/searching
    if count > 0:
        ws.auto_filter.ref = f"B5:F{row - 1}"


# -----------------------------------------------------------------------
# Sheet 5: Bills
# -----------------------------------------------------------------------

def _build_bills_sheet(wb: Workbook, cfo: "CFO") -> None:
    ws = wb.create_sheet("Bills")
    ws.sheet_properties.tabColor = "8B5CF6"

    _set_col_widths(ws, {"A": 4, "B": 30, "C": 16, "D": 16, "E": 16, "F": 14, "G": 14})

    ws.merge_cells("B2:G2")
    ws.cell(row=2, column=2, value="Your Bills").font = _TITLE_FONT
    ws.cell(row=3, column=2, value="Everything you pay regularly").font = _SUBTITLE_FONT

    _write_header_row(ws, 5, ["Bill", "Amount", "Due Date", "How Often", "Auto-Pay?", "Status"], start_col=2)

    today = datetime.now(timezone.utc).isoformat()[:10]

    bills = sorted(cfo._bills, key=lambda b: b.due_date)
    row = 6
    for b in bills:
        if b.paid:
            status = "Paid"
        elif b.due_date < today:
            status = "OVERDUE"
        else:
            status = "Upcoming"

        auto_pay = "Yes" if b.auto_pay else "No"
        freq = b.frequency.title() if b.frequency else "One-time"

        _write_data_row(ws, row, [b.name, b.amount, b.due_date, freq, auto_pay, status],
                        start_col=2, stripe=(row % 2 == 0))

        # Color overdue bills red
        if status == "OVERDUE":
            for col in range(2, 8):
                ws.cell(row=row, column=col).fill = _LIGHT_RED
            ws.cell(row=row, column=7).font = Font(name="Calibri", size=11, bold=True, color="DC2626")
        elif status == "Paid":
            ws.cell(row=row, column=7).font = Font(name="Calibri", size=11, color="16A34A")
        elif not b.auto_pay:
            ws.cell(row=row, column=6).fill = _LIGHT_YELLOW
            ws.cell(row=row, column=6).font = Font(name="Calibri", size=11, bold=True, color="92400E")

        row += 1

    if not bills:
        ws.cell(row=6, column=2, value="No bills tracked yet.").font = _BODY_FONT
        ws.cell(row=7, column=2, value="Add bills through the CFO agent to track them here.").font = _SUBTITLE_FONT

    # Monthly total
    if bills:
        monthly_total = sum(b.amount for b in bills if b.recurring and b.frequency == "monthly")
        row += 1
        ws.cell(row=row, column=2, value="Total Monthly Bills").font = _BODY_BOLD
        t = ws.cell(row=row, column=3, value=monthly_total)
        t.number_format = _MONEY_FORMAT
        t.font = Font(name="Calibri", size=12, bold=True, color="1E293B")
        t.border = Border(top=Side(style="double", color="334155"))


# -----------------------------------------------------------------------
# Sheet 6: Trends (month-by-month)
# -----------------------------------------------------------------------

def _build_trends_sheet(wb: Workbook, cfo: "CFO") -> None:
    ws = wb.create_sheet("Trends")
    ws.sheet_properties.tabColor = "06B6D4"

    _set_col_widths(ws, {"A": 4, "B": 16, "C": 18, "D": 18, "E": 18, "F": 4, "G": 4, "H": 16, "I": 20})

    ws.merge_cells("B2:E2")
    ws.cell(row=2, column=2, value="Monthly Trends").font = _TITLE_FONT
    ws.cell(row=3, column=2, value="How your spending and income change month to month").font = _SUBTITLE_FONT

    # --- Income vs Spending by month ---
    months: dict[str, dict[str, float]] = {}
    for tx in cfo._transactions:
        month = tx.date[:7]  # YYYY-MM
        if month not in months:
            months[month] = {"income": 0, "spending": 0}
        if tx.amount > 0:
            months[month]["income"] += tx.amount
        else:
            months[month]["spending"] += abs(tx.amount)

    if not months:
        ws.cell(row=5, column=2, value="No transactions yet — trends will appear after syncing.").font = _BODY_FONT
    else:
        _write_header_row(ws, 5, ["Month", "Income", "Spending", "Left Over"], start_col=2)

        row = 6
        for month_key in sorted(months.keys()):
            data = months[month_key]
            income = data["income"]
            spending = data["spending"]
            left_over = income - spending

            try:
                dt = datetime.strptime(month_key, "%Y-%m")
                month_label = dt.strftime("%b %Y")
            except ValueError:
                month_label = month_key

            _write_data_row(ws, row, [month_label, income, spending, left_over],
                            start_col=2, stripe=(row % 2 == 0))

            ws.cell(row=row, column=3).font = Font(name="Calibri", size=11, color="16A34A")
            ws.cell(row=row, column=4).font = Font(name="Calibri", size=11, color="DC2626")
            lo_cell = ws.cell(row=row, column=5)
            if left_over >= 0:
                lo_cell.font = Font(name="Calibri", size=11, bold=True, color="16A34A")
                lo_cell.fill = _LIGHT_GREEN
            else:
                lo_cell.font = Font(name="Calibri", size=11, bold=True, color="DC2626")
                lo_cell.fill = _LIGHT_RED

            row += 1

        # Bar chart
        if len(months) > 1:
            chart = BarChart()
            chart.type = "col"
            chart.title = "Income vs Spending"
            chart.y_axis.title = "Dollars"
            chart.x_axis.title = "Month"
            chart.style = 10
            chart.width = 22
            chart.height = 14

            income_data = Reference(ws, min_col=3, min_row=5, max_row=row - 1)
            spending_data = Reference(ws, min_col=4, min_row=5, max_row=row - 1)
            months_labels = Reference(ws, min_col=2, min_row=6, max_row=row - 1)

            chart.add_data(income_data, titles_from_data=True)
            chart.add_data(spending_data, titles_from_data=True)
            chart.set_categories(months_labels)

            chart.series[0].graphicalProperties.solidFill = "22C55E"
            chart.series[1].graphicalProperties.solidFill = "EF4444"

            ws.add_chart(chart, f"B{row + 2}")

    # --- Net Worth Over Time ---
    nw_trend = cfo.net_worth_trend(months=12)
    if nw_trend:
        ws.merge_cells("H2:I2")
        ws.cell(row=2, column=8, value="Net Worth Over Time").font = _TITLE_FONT

        _write_header_row(ws, 5, ["Date", "Net Worth"], start_col=8)

        nw_row = 6
        for snap in nw_trend:
            try:
                dt = datetime.strptime(snap["date"], "%Y-%m-%d")
                date_label = dt.strftime("%b %d, %Y")
            except ValueError:
                date_label = snap["date"]

            _write_data_row(ws, nw_row, [date_label, snap["net_worth"]],
                            start_col=8, stripe=(nw_row % 2 == 0))

            nw_cell = ws.cell(row=nw_row, column=9)
            if snap["net_worth"] >= 0:
                nw_cell.font = Font(name="Calibri", size=11, bold=True, color="16A34A")
            else:
                nw_cell.font = Font(name="Calibri", size=11, bold=True, color="DC2626")

            nw_row += 1

        # Line chart for net worth trend
        if len(nw_trend) > 1:
            from openpyxl.chart import LineChart
            chart = LineChart()
            chart.title = "Net Worth Trend"
            chart.y_axis.title = "Net Worth ($)"
            chart.style = 10
            chart.width = 20
            chart.height = 12

            nw_data = Reference(ws, min_col=9, min_row=5, max_row=nw_row - 1)
            nw_labels = Reference(ws, min_col=8, min_row=6, max_row=nw_row - 1)
            chart.add_data(nw_data, titles_from_data=True)
            chart.set_categories(nw_labels)

            chart.series[0].graphicalProperties.line.solidFill = "3B82F6"
            chart.series[0].graphicalProperties.line.width = 25000  # 2.5pt

            ws.add_chart(chart, f"H{nw_row + 2}")
