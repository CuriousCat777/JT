"""Shared CLI formatting utilities for Guardian One.

Provides consistent output formatting across all CLI commands.
Follows the Guardian One Design System v1.0 — CLI Design Language.

Usage:
    from guardian_one.utils.formatting import (
        format_currency, format_percent, format_status,
        format_separator, format_header, format_table,
    )

    print(format_header("CFO VALIDATION REPORT"))
    print(format_status("ok", "Sync complete"))
    print(format_currency(95162.01))
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ----------------------------------------------------------------
# ANSI escape codes
# ----------------------------------------------------------------

_ANSI = {
    "reset":   "\033[0m",
    "bold":    "\033[1m",
    "green":   "\033[32m",
    "red":     "\033[31m",
    "yellow":  "\033[33m",
    "blue":    "\033[34m",
    "cyan":    "\033[36m",
    "gray":    "\033[90m",
    "white":   "\033[1;37m",
}


def _c(text: str, code: str) -> str:
    """Wrap *text* in an ANSI escape sequence."""
    return f"{_ANSI.get(code, '')}{text}{_ANSI['reset']}"


# ----------------------------------------------------------------
# Status vocabulary  (Design System § 3.6)
# ----------------------------------------------------------------

# Canonical status map: (label, icon, ansi_color)
_STATUS_MAP: dict[str, tuple[str, str, str]] = {
    "ok":       ("OK",      "[OK]",     "green"),
    "online":   ("Online",  "[OK]",     "green"),
    "success":  ("OK",      "[OK]",     "green"),
    "failed":   ("FAILED",  "[FAILED]", "red"),
    "offline":  ("Offline", "[FAILED]", "red"),
    "error":    ("ERROR",   "[FAILED]", "red"),
    "warning":  ("WARN",    "[WARN]",   "yellow"),
    "warn":     ("WARN",    "[WARN]",   "yellow"),
    "degraded": ("WARN",    "[WARN]",   "yellow"),
    "idle":     ("IDLE",    "[IDLE]",   "yellow"),
    "disabled": ("DISABLED","[IDLE]",   "yellow"),
    "paused":   ("PAUSED",  "[IDLE]",   "yellow"),
    "syncing":  ("SYNC",    "[SYNC]",   "cyan"),
    "running":  ("SYNC",    "[SYNC]",   "cyan"),
    "info":     ("INFO",    "[INFO]",   "blue"),
    "overdue":  ("OVERDUE", "[!]",      "red"),
    "critical": ("CRITICAL","[!!]",     "red"),
}


def format_status(status: str, message: str = "") -> str:
    """Render a status badge with optional message.

    >>> format_status("ok", "Sync complete")
    '  [OK] Sync complete'           # with green ANSI
    """
    key = status.lower()
    _, icon, color = _STATUS_MAP.get(key, ("???", "[???]", "gray"))
    badge = _c(icon, color)
    if message:
        return f"  {badge} {message}"
    return f"  {badge}"


def status_icon(status: str) -> str:
    """Return just the colored icon for inline use.

    >>> status_icon("ok")
    '[OK]'  # green
    """
    key = status.lower()
    _, icon, color = _STATUS_MAP.get(key, ("???", "[???]", "gray"))
    return _c(icon, color)


# ----------------------------------------------------------------
# Number formatting  (Design System § 3.6)
# ----------------------------------------------------------------

def format_currency(value: float, width: int = 12) -> str:
    """Right-aligned currency: ``$  95,162.01``.

    >>> format_currency(95162.01)
    '$  95,162.01'
    """
    formatted = f"${value:>{width},.2f}"
    return formatted


def format_percent(value: float, width: int = 6) -> str:
    """Right-aligned percentage: `` 42.5%``."""
    return f"{value:>{width}.1f}%"


def format_count(value: int, width: int = 6) -> str:
    """Right-aligned count: `` 1,234``."""
    return f"{value:>{width},d}"


# ----------------------------------------------------------------
# Separators  (Design System § 5.1)
# ----------------------------------------------------------------

def format_separator(char: str = "=", width: int = 60) -> str:
    """Major (``=``) or minor (``-``) separator line, indented."""
    return f"  {char * width}"


def format_header(title: str, width: int = 60) -> str:
    """Full section header with top/bottom separators.

    ::

        ============================================================
          CFO VALIDATION REPORT — Guardian One
        ============================================================
    """
    bar = format_separator("=", width)
    return f"{bar}\n    {title}\n{bar}"


def format_section(title: str, width: int = 40) -> str:
    """Sub-section header with a minor separator.

    ::

        NET WORTH SUMMARY
        ----------------------------------------
    """
    return f"\n  {_c(title, 'white')}\n  {'-' * width}"


# ----------------------------------------------------------------
# Tables  (Design System § 3.6)
# ----------------------------------------------------------------

def format_table(
    headers: list[str],
    rows: list[list[Any]],
    alignments: list[str] | None = None,
    widths: list[int] | None = None,
    footer: list[Any] | None = None,
) -> str:
    """Render an aligned ASCII table.

    Args:
        headers: Column names.
        rows: List of row values (same length as headers).
        alignments: ``"<"`` (left), ``">"`` (right), ``"^"`` (center)
                    per column. Defaults to left.
        widths: Column widths. Defaults to max(header, data) + 2.
        footer: Optional summary row rendered below a separator.

    Returns:
        Multi-line string ready for ``print()``.
    """
    n_cols = len(headers)
    if alignments is None:
        alignments = ["<"] * n_cols
    if widths is None:
        widths = [
            max(
                len(str(headers[i])),
                *(len(str(row[i])) for row in rows),
                len(str(footer[i])) if footer else 0,
            ) + 2
            for i in range(n_cols)
        ]

    def _fmt_row(cells: list[Any]) -> str:
        parts = []
        for i, cell in enumerate(cells):
            w = widths[i]
            a = alignments[i]
            parts.append(f"{str(cell):{a}{w}}")
        return "  " + "".join(parts)

    total_width = sum(widths)
    lines = [
        _fmt_row(headers),
        "  " + "-" * total_width,
    ]
    for row in rows:
        lines.append(_fmt_row(row))
    if footer:
        lines.append("  " + "-" * total_width)
        lines.append(_fmt_row(footer))
    return "\n".join(lines)


# ----------------------------------------------------------------
# Timestamps
# ----------------------------------------------------------------

def format_timestamp(dt: datetime | None = None) -> str:
    """ISO 8601 UTC timestamp string."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_relative_time(iso_str: str) -> str:
    """Convert ISO timestamp to relative string like ``2m ago``."""
    try:
        then = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return iso_str
    now = datetime.now(timezone.utc)
    delta = now - then
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


# ----------------------------------------------------------------
# Agent report helpers
# ----------------------------------------------------------------

def format_agent_report_brief(name: str, report: Any) -> str:
    """One-line agent report summary matching Design System status vocab.

    Replaces ad-hoc ``print(f"  [{name}] {status} ...")`` calls.
    """
    status_str = str(report.status).lower()
    alerts = len(report.alerts) if report.alerts else 0
    line = format_status(status_str, f"{name} — {report.summary}")
    if alerts:
        line += f"  ({alerts} alert{'s' if alerts > 1 else ''})"
    return line
