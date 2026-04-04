"""Content gate — centralized PII/PHI detection and redaction.

This module provides system-wide protection against PII leakage into
audit logs, external syncs, and agent reports.  It is the single source
of truth for what constitutes sensitive data and how it should be masked.

Design principles:
    - Patterns are intentionally broad to catch edge cases (false positives
      are acceptable; false negatives are not)
    - Redaction is one-way — original values cannot be recovered from masked output
    - All agents and the audit system route through this gate
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# PII pattern definitions
# ---------------------------------------------------------------------------

# Each entry: (name, compiled regex, replacement label)
_PII_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Social Security Numbers
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN-REDACTED]"),
    ("ssn_nodash", re.compile(r"\b\d{9}\b"), "[SSN-REDACTED]"),

    # Credit / debit card numbers (13–19 digits, with optional separators)
    ("credit_card", re.compile(
        r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7}\b"
    ), "[CARD-REDACTED]"),

    # Bank routing / account numbers
    ("bank_account", re.compile(
        r"\b(?:routing|account|acct)\s*#?\s*:?\s*\d{9,17}\b", re.IGNORECASE
    ), "[ACCOUNT-REDACTED]"),

    # Email addresses
    ("email", re.compile(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
    ), "[EMAIL-REDACTED]"),

    # Phone numbers (US formats)
    ("phone", re.compile(
        r"\b(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b"
    ), "[PHONE-REDACTED]"),

    # Medical record numbers
    ("mrn", re.compile(
        r"\b(?:MRN|medical\s*record)\s*[:#]?\s*\d+\b", re.IGNORECASE
    ), "[MRN-REDACTED]"),
    ("mrn_code", re.compile(r"\b[A-Z]{1,2}\d{6,10}\b"), "[MRN-REDACTED]"),

    # Membership / loyalty numbers (common formats)
    ("membership", re.compile(
        r"\b(?:member(?:ship)?|loyalty|cardless)\s*(?:number|no|#|id|code)\s*:?\s*[\w\-]{6,}\b",
        re.IGNORECASE,
    ), "[MEMBERSHIP-REDACTED]"),

    # IP addresses (v4)
    ("ipv4", re.compile(
        r"\b(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d\d?)){3}\b"
    ), "[IP-REDACTED]"),

    # Date of birth patterns
    ("dob", re.compile(
        r"\b(?:DOB|date\s*of\s*birth|born)\s*:?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",
        re.IGNORECASE,
    ), "[DOB-REDACTED]"),
]

# Owner identity patterns — the user's known PII that should always be masked
# in external-facing outputs and audit logs.
_OWNER_NAME_VARIANTS: list[str] = [
    "Jeremy Paulo Salvino Tabernero",
    "Jeremy Tabernero",
    "Jeremy Paulo Tabernero",
    "J. Tabernero",
    "JEREMY TABERNERO",
    "JEREMY PAULO TABERNERO",
    "jeremytabernero",
    "jeremy_paulo21",
    "JEREMY_PAULO21",
]

_OWNER_EMAIL_VARIANTS: list[str] = [
    "jeremytabernero@gmail.com",
    "jeremy_paulo21@yahoo.com",
]

# Compile owner patterns (case-insensitive).
# Email patterns MUST come before name patterns so that
# "jeremytabernero@gmail.com" is matched as an email, not partially
# consumed by the "jeremytabernero" name pattern.
_OWNER_PATTERNS: list[tuple[str, re.Pattern[str], str]] = []
for _email in _OWNER_EMAIL_VARIANTS:
    _OWNER_PATTERNS.append((
        "owner_email",
        re.compile(re.escape(_email), re.IGNORECASE),
        "[OWNER-EMAIL-REDACTED]",
    ))
for _name in _OWNER_NAME_VARIANTS:
    _OWNER_PATTERNS.append((
        "owner_name",
        re.compile(re.escape(_name), re.IGNORECASE),
        "[OWNER-NAME-REDACTED]",
    ))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def redact_text(text: str, *, include_owner: bool = True) -> str:
    """Replace all detected PII patterns in *text* with redaction labels.

    Args:
        text: The string to scan and redact.
        include_owner: If True (default), also redact known owner identity
            patterns (name variants, known email addresses).

    Returns:
        A copy of *text* with all PII replaced by bracketed labels.
    """
    if not text:
        return text

    result = text

    # Owner-specific patterns first (more specific → applied first)
    if include_owner:
        for _name, pattern, replacement in _OWNER_PATTERNS:
            result = pattern.sub(replacement, result)

    # General PII patterns
    for _name, pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)

    return result


def redact_dict(
    data: dict[str, Any],
    *,
    include_owner: bool = True,
    _depth: int = 0,
) -> dict[str, Any]:
    """Recursively redact PII from all string values in a dict.

    Handles nested dicts and lists up to 10 levels deep.
    Non-string, non-container values are passed through unchanged.
    """
    if _depth > 10:
        return data

    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = redact_text(value, include_owner=include_owner)
        elif isinstance(value, dict):
            result[key] = redact_dict(
                value, include_owner=include_owner, _depth=_depth + 1
            )
        elif isinstance(value, list):
            result[key] = _redact_list(
                value, include_owner=include_owner, _depth=_depth + 1
            )
        else:
            result[key] = value
    return result


def _redact_list(
    items: list[Any],
    *,
    include_owner: bool = True,
    _depth: int = 0,
) -> list[Any]:
    """Redact PII from string elements in a list (recursive)."""
    if _depth > 10:
        return items

    result: list[Any] = []
    for item in items:
        if isinstance(item, str):
            result.append(redact_text(item, include_owner=include_owner))
        elif isinstance(item, dict):
            result.append(
                redact_dict(item, include_owner=include_owner, _depth=_depth + 1)
            )
        elif isinstance(item, list):
            result.append(
                _redact_list(item, include_owner=include_owner, _depth=_depth + 1)
            )
        else:
            result.append(item)
    return result


def contains_pii(text: str, *, include_owner: bool = True) -> bool:
    """Return True if *text* contains any detectable PII pattern."""
    if not text:
        return False

    if include_owner:
        for _name, pattern, _repl in _OWNER_PATTERNS:
            if pattern.search(text):
                return True

    for _name, pattern, _repl in _PII_PATTERNS:
        if pattern.search(text):
            return True

    return False


def scan_pii(text: str, *, include_owner: bool = True) -> list[dict[str, str]]:
    """Scan *text* and return a list of detected PII findings.

    Each finding is a dict with keys: ``type``, ``matched``, ``replacement``.
    Useful for audit trails that need to record *what* was found without
    preserving the actual sensitive value.
    """
    if not text:
        return []

    findings: list[dict[str, str]] = []

    if include_owner:
        for pii_type, pattern, replacement in _OWNER_PATTERNS:
            for match in pattern.finditer(text):
                findings.append({
                    "type": pii_type,
                    "matched": f"[{len(match.group())} chars]",
                    "replacement": replacement,
                })

    for pii_type, pattern, replacement in _PII_PATTERNS:
        for match in pattern.finditer(text):
            findings.append({
                "type": pii_type,
                "matched": f"[{len(match.group())} chars]",
                "replacement": replacement,
            })

    return findings
