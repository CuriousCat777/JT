"""LLM triage — AI-assisted alert classification and summarization.

Safety: LLM recommends actions only. It NEVER executes containment
or destructive operations directly.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class TriageResult:
    """LLM triage output for a security event."""
    severity: str
    attack_type: str
    recommended_action: str
    confidence: float  # 0.0 to 1.0
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "attack_type": self.attack_type,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence,
            "summary": self.summary,
        }


_TRIAGE_PROMPT = """Analyze this security event and provide a triage assessment.

Event:
{event_json}

Respond with ONLY a JSON object (no other text):
{{
  "severity": "low|medium|high|critical",
  "attack_type": "MITRE ATT&CK technique name or 'benign'",
  "recommended_action": "brief action to take",
  "confidence": 0.0-1.0,
  "summary": "one sentence summary"
}}"""


class LLMTriage:
    """Uses LLM reasoning to triage security alerts."""

    def triage_event(
        self,
        think_fn: Callable[[str, dict[str, Any] | None], str],
        event: dict[str, Any],
    ) -> TriageResult | None:
        """Triage a security event using the agent's think_quick method.

        Args:
            think_fn: The agent's think_quick callable.
            event: The event dict to triage.

        Returns:
            TriageResult or None if LLM is unavailable.
        """
        prompt = _TRIAGE_PROMPT.format(event_json=json.dumps(event, indent=2))

        response = think_fn(prompt, None)
        if not response:
            return None

        return self._parse_response(response)

    def _parse_response(self, text: str) -> TriageResult | None:
        """Parse LLM JSON response into a TriageResult."""
        try:
            # Strip markdown code fences if present
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
                clean = clean.rsplit("```", 1)[0]

            data = json.loads(clean)
            return TriageResult(
                severity=data.get("severity", "medium"),
                attack_type=data.get("attack_type", "unknown"),
                recommended_action=data.get("recommended_action", "investigate"),
                confidence=float(data.get("confidence", 0.5)),
                summary=data.get("summary", ""),
            )
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            log.warning("Failed to parse LLM triage response: %s", e)
            return None
