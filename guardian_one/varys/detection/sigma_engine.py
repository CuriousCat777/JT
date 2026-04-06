"""Sigma rule engine — loads YAML rules and matches events."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

RULES_DIR = Path(__file__).parent / "rules"


@dataclass
class SigmaMatch:
    """Result of a Sigma rule match."""
    rule_id: str
    title: str
    description: str
    level: str  # low, medium, high, critical
    technique: str  # MITRE ATT&CK technique ID
    tags: list[str]


@dataclass
class SigmaRule:
    """Parsed Sigma rule."""
    id: str
    title: str
    description: str
    level: str
    tags: list[str]
    technique: str
    logsource_category: str
    detection_fields: dict[str, list[str]]

    def matches(self, event: dict[str, Any]) -> bool:
        """Check if an event matches this rule's detection logic."""
        for field_name, patterns in self.detection_fields.items():
            event_value = str(event.get(field_name, "")).lower()
            if not event_value:
                return False
            if not any(p.lower() in event_value for p in patterns):
                return False
        return True


class SigmaEngine:
    """Loads and evaluates Sigma detection rules."""

    def __init__(self) -> None:
        self._rules: list[SigmaRule] = []

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def load_rules(self, rules_dir: Path | None = None) -> None:
        """Load all YAML rules from the rules directory."""
        directory = rules_dir or RULES_DIR
        if not directory.exists():
            log.warning("Rules directory %s does not exist", directory)
            return

        for rule_file in sorted(directory.glob("*.yaml")):
            try:
                rule = self._parse_rule(rule_file)
                if rule:
                    self._rules.append(rule)
            except Exception as e:
                log.error("Failed to parse rule %s: %s", rule_file.name, e)

        log.info("Loaded %d Sigma rules", len(self._rules))

    def match(self, event: dict[str, Any]) -> list[SigmaMatch]:
        """Run all rules against an event, return matches."""
        matches = []
        for rule in self._rules:
            if rule.matches(event):
                matches.append(SigmaMatch(
                    rule_id=rule.id,
                    title=rule.title,
                    description=rule.description,
                    level=rule.level,
                    technique=rule.technique,
                    tags=rule.tags,
                ))
        return matches

    def get_rules(self) -> list[dict[str, Any]]:
        """Return all rules as dicts for the API."""
        return [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "level": r.level,
                "technique": r.technique,
                "tags": r.tags,
            }
            for r in self._rules
        ]

    def _parse_rule(self, path: Path) -> SigmaRule | None:
        """Parse a single Sigma YAML rule."""
        with open(path) as f:
            raw = yaml.safe_load(f)

        if not raw or "detection" not in raw:
            return None

        tags = raw.get("tags", [])
        technique = ""
        for tag in tags:
            if tag.startswith("attack.t"):
                technique = tag.replace("attack.", "").upper()
                break

        detection = raw["detection"]
        selection = detection.get("selection", {})
        fields: dict[str, list[str]] = {}
        for key, value in selection.items():
            # Handle Sigma field modifiers like "CommandLine|contains"
            field_name = key.split("|")[0]
            if isinstance(value, list):
                fields[field_name] = [str(v) for v in value]
            else:
                fields[field_name] = [str(value)]

        return SigmaRule(
            id=raw.get("id", path.stem),
            title=raw.get("title", path.stem),
            description=raw.get("description", ""),
            level=raw.get("level", "medium"),
            tags=tags,
            technique=technique,
            logsource_category=raw.get("logsource", {}).get("category", ""),
            detection_fields=fields,
        )
