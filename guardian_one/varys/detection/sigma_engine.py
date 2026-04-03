"""Sigma-style rule engine for deterministic threat detection.

Rules are defined as dataclasses with field matchers. The engine
evaluates each incoming SecurityEvent against all loaded rules and
produces Alert objects when matches are found.

This is a lightweight implementation inspired by the Sigma rule format
(https://sigmahq.io) but operates on SecurityEvent objects directly
rather than raw log lines.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from guardian_one.varys.models import Alert, AlertSeverity, SecurityEvent

logger = logging.getLogger(__name__)


@dataclass
class SigmaRule:
    """A detection rule in Sigma-inspired format.

    Fields:
        rule_id: Unique identifier (e.g. "VARYS-001").
        name: Human-readable rule name.
        description: What this rule detects.
        severity: Alert severity when triggered.
        mitre_tactic: MITRE ATT&CK tactic ID (e.g. "TA0006").
        mitre_technique: MITRE ATT&CK technique ID (e.g. "T1110").
        conditions: Dict of field_name → value/pattern matchers.
        threshold: Number of matching events within window to trigger.
        enabled: Whether this rule is active.
    """
    rule_id: str = ""
    name: str = ""
    description: str = ""
    severity: AlertSeverity = AlertSeverity.MEDIUM
    mitre_tactic: str = ""
    mitre_technique: str = ""
    conditions: dict[str, Any] = field(default_factory=dict)
    threshold: int = 1
    enabled: bool = True


def _field_matches(event_value: Any, condition_value: Any) -> bool:
    """Check if an event field matches a condition value.

    Supports:
    - Exact string match
    - List of values (OR match)
    - Regex patterns (prefixed with "re:")
    - Contains match (prefixed with "contains:")
    """
    if event_value is None:
        return False

    event_str = str(event_value)

    # List of values — match any
    if isinstance(condition_value, list):
        return any(_field_matches(event_value, v) for v in condition_value)

    cond_str = str(condition_value)

    # Regex match
    if cond_str.startswith("re:"):
        pattern = cond_str[3:]
        return bool(re.search(pattern, event_str, re.IGNORECASE))

    # Contains match
    if cond_str.startswith("contains:"):
        substring = cond_str[9:]
        return substring.lower() in event_str.lower()

    # Exact match (case-insensitive)
    return event_str.lower() == cond_str.lower()


class SigmaEngine:
    """Evaluate SecurityEvents against loaded Sigma-style rules."""

    def __init__(self) -> None:
        self._rules: list[SigmaRule] = []
        self._event_buffer: dict[str, list[SecurityEvent]] = {}
        self._total_matches: int = 0

    @property
    def rules(self) -> list[SigmaRule]:
        return list(self._rules)

    @property
    def total_matches(self) -> int:
        return self._total_matches

    def load_rule(self, rule: SigmaRule) -> None:
        """Add a rule to the engine."""
        self._rules.append(rule)

    def load_rules(self, rules: list[SigmaRule]) -> None:
        """Add multiple rules."""
        self._rules.extend(rules)

    def load_builtin_rules(self) -> None:
        """Load the default VARYS rule pack."""
        self._rules.extend(_BUILTIN_RULES)

    def evaluate(self, event: SecurityEvent) -> list[Alert]:
        """Evaluate an event against all rules. Returns any triggered alerts."""
        alerts: list[Alert] = []

        for rule in self._rules:
            if not rule.enabled:
                continue

            if self._matches(event, rule):
                # Threshold tracking
                buf = self._event_buffer.setdefault(rule.rule_id, [])
                buf.append(event)

                if len(buf) >= rule.threshold:
                    alert = Alert(
                        title=rule.name,
                        description=rule.description,
                        severity=rule.severity,
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        mitre_tactic=rule.mitre_tactic,
                        mitre_technique=rule.mitre_technique,
                        events=list(buf),
                        source_ip=event.source_ip,
                        source_user=event.source_user,
                        host_name=event.host_name,
                    )
                    alerts.append(alert)
                    self._total_matches += 1
                    # Reset buffer after alert fires
                    self._event_buffer[rule.rule_id] = []

        return alerts

    def evaluate_batch(self, events: list[SecurityEvent]) -> list[Alert]:
        """Evaluate a batch of events."""
        alerts: list[Alert] = []
        for event in events:
            alerts.extend(self.evaluate(event))
        return alerts

    @staticmethod
    def _matches(event: SecurityEvent, rule: SigmaRule) -> bool:
        """Check if an event matches all conditions of a rule (AND logic)."""
        for field_name, expected in rule.conditions.items():
            actual = getattr(event, field_name, None)

            # Support nested tag matching
            if field_name == "tags" and isinstance(expected, (str, list)):
                event_tags = event.tags or []
                if isinstance(expected, str):
                    if expected not in event_tags:
                        return False
                else:
                    if not any(t in event_tags for t in expected):
                        return False
                continue

            if not _field_matches(actual, expected):
                return False

        return True

    def clear_buffers(self) -> None:
        """Reset all threshold tracking buffers."""
        self._event_buffer.clear()


# ── Built-in rule pack ──────────────────────────────────────────────

_BUILTIN_RULES: list[SigmaRule] = [
    SigmaRule(
        rule_id="VARYS-001",
        name="SSH Brute Force Attempt",
        description="Multiple failed SSH login attempts detected — possible brute force attack.",
        severity=AlertSeverity.HIGH,
        mitre_tactic="TA0006",       # Credential Access
        mitre_technique="T1110",     # Brute Force
        conditions={
            "category": "authentication",
            "action": "login_failed",
            "tags": "ssh",
        },
        threshold=5,
    ),
    SigmaRule(
        rule_id="VARYS-002",
        name="Suspicious Privilege Escalation",
        description="Dangerous command executed via sudo (chmod 777, rm -rf, etc.)",
        severity=AlertSeverity.HIGH,
        mitre_tactic="TA0004",       # Privilege Escalation
        mitre_technique="T1548",     # Abuse Elevation Control
        conditions={
            "category": "process",
            "action": "sudo_exec",
            "tags": "dangerous_command",
        },
    ),
    SigmaRule(
        rule_id="VARYS-003",
        name="New User Account Created",
        description="A new user account was created — verify this was authorized.",
        severity=AlertSeverity.MEDIUM,
        mitre_tactic="TA0003",       # Persistence
        mitre_technique="T1136",     # Create Account
        conditions={
            "category": "iam",
            "action": "user_created",
        },
    ),
    SigmaRule(
        rule_id="VARYS-004",
        name="SSH Login from Unusual Source",
        description="Successful SSH login detected — verify the source IP is trusted.",
        severity=AlertSeverity.MEDIUM,
        mitre_tactic="TA0001",       # Initial Access
        mitre_technique="T1078",     # Valid Accounts
        conditions={
            "category": "authentication",
            "action": "login_success",
            "tags": "ssh",
        },
    ),
    SigmaRule(
        rule_id="VARYS-005",
        name="Firewall Connection Blocked",
        description="Network connection blocked by firewall — possible scanning or attack.",
        severity=AlertSeverity.LOW,
        mitre_tactic="TA0043",       # Reconnaissance
        mitre_technique="T1046",     # Network Service Discovery
        conditions={
            "category": "network",
            "action": "firewall_drop",
        },
        threshold=10,
    ),
    SigmaRule(
        rule_id="VARYS-006",
        name="Process Crash (Segfault)",
        description="A process crashed with a segmentation fault — possible exploit attempt.",
        severity=AlertSeverity.MEDIUM,
        mitre_tactic="TA0002",       # Execution
        mitre_technique="T1203",     # Exploitation for Client Execution
        conditions={
            "category": "process",
            "action": "segfault",
        },
    ),
    SigmaRule(
        rule_id="VARYS-007",
        name="Wazuh Critical Alert",
        description="Wazuh detected a critical-severity event.",
        severity=AlertSeverity.CRITICAL,
        mitre_tactic="",
        mitre_technique="",
        conditions={
            "source": "wazuh",
            "severity": "critical",
        },
    ),
]
