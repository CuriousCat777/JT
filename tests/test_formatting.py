"""Tests for guardian_one.utils.formatting — Design System CLI formatters."""

from dataclasses import dataclass

from guardian_one.utils.formatting import (
    format_currency,
    format_percent,
    format_count,
    format_separator,
    format_header,
    format_section,
    format_status,
    format_table,
    format_timestamp,
    format_relative_time,
    format_agent_report_brief,
    status_icon,
)


# ---------------------------------------------------------------
# Currency / numbers
# ---------------------------------------------------------------

def test_format_currency_positive():
    result = format_currency(95162.01)
    assert "95,162.01" in result
    assert result.startswith("$")


def test_format_currency_negative():
    result = format_currency(-3361.98)
    assert "-3,361.98" in result


def test_format_currency_zero():
    assert "0.00" in format_currency(0)


def test_format_percent():
    result = format_percent(42.5)
    assert "42.5%" in result


def test_format_count():
    result = format_count(1234)
    assert "1,234" in result


# ---------------------------------------------------------------
# Separators / headers
# ---------------------------------------------------------------

def test_format_separator_default():
    result = format_separator()
    assert "=" * 60 in result
    assert result.startswith("  ")


def test_format_separator_custom():
    result = format_separator("-", 40)
    assert "-" * 40 in result


def test_format_header():
    result = format_header("TEST REPORT")
    lines = result.split("\n")
    assert len(lines) == 3
    assert "TEST REPORT" in lines[1]
    assert "=" * 60 in lines[0]
    assert "=" * 60 in lines[2]


def test_format_section():
    result = format_section("NET WORTH")
    assert "NET WORTH" in result
    assert "-" * 40 in result


# ---------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------

def test_format_status_ok():
    result = format_status("ok", "All systems go")
    assert "[OK]" in result
    assert "All systems go" in result


def test_format_status_failed():
    result = format_status("failed", "Connection refused")
    assert "[FAILED]" in result


def test_format_status_warning():
    result = format_status("warning", "Approaching limit")
    assert "[WARN]" in result


def test_format_status_idle():
    result = format_status("idle")
    assert "[IDLE]" in result


def test_format_status_syncing():
    result = format_status("syncing", "In progress")
    assert "[SYNC]" in result


def test_format_status_overdue():
    result = format_status("overdue", "Bill payment")
    assert "[!]" in result


def test_format_status_unknown():
    result = format_status("nonexistent")
    assert "[???]" in result


def test_status_icon():
    icon = status_icon("ok")
    assert "[OK]" in icon


def test_format_status_case_insensitive():
    result = format_status("OK", "test")
    assert "[OK]" in result


# ---------------------------------------------------------------
# Tables
# ---------------------------------------------------------------

def test_format_table_basic():
    result = format_table(
        headers=["Name", "Balance"],
        rows=[
            ["Checking", "$3,420.15"],
            ["Savings", "$12,800.00"],
        ],
    )
    assert "Name" in result
    assert "Balance" in result
    assert "Checking" in result
    assert "$12,800.00" in result
    assert "---" in result


def test_format_table_with_footer():
    result = format_table(
        headers=["Account", "Amount"],
        rows=[["A", "$100"], ["B", "$200"]],
        footer=["TOTAL", "$300"],
    )
    assert "TOTAL" in result
    assert "$300" in result


def test_format_table_alignments():
    result = format_table(
        headers=["Name", "Value"],
        rows=[["Test", "42"]],
        alignments=["<", ">"],
        widths=[20, 10],
    )
    lines = result.strip().split("\n")
    assert len(lines) == 3  # header + separator + 1 row


# ---------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------

def test_format_timestamp():
    ts = format_timestamp()
    assert "T" in ts
    assert ts.endswith("Z")


def test_format_relative_time_seconds():
    from datetime import datetime, timezone, timedelta
    recent = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    result = format_relative_time(recent)
    assert "s ago" in result


def test_format_relative_time_minutes():
    from datetime import datetime, timezone, timedelta
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    result = format_relative_time(past)
    assert "m ago" in result


def test_format_relative_time_invalid():
    result = format_relative_time("not-a-date")
    assert result == "not-a-date"


# ---------------------------------------------------------------
# Agent report brief
# ---------------------------------------------------------------

@dataclass
class _FakeReport:
    status: str = "ok"
    summary: str = "All good"
    alerts: list = None

    def __post_init__(self):
        if self.alerts is None:
            self.alerts = []


def test_format_agent_report_brief_no_alerts():
    result = format_agent_report_brief("cfo", _FakeReport())
    assert "[OK]" in result
    assert "cfo" in result
    assert "All good" in result


def test_format_agent_report_brief_with_alerts():
    result = format_agent_report_brief("cfo", _FakeReport(alerts=["a", "b"]))
    assert "2 alerts" in result


def test_format_agent_report_brief_error():
    result = format_agent_report_brief("chronos", _FakeReport(status="error", summary="Timeout"))
    assert "[FAILED]" in result
    assert "Timeout" in result
