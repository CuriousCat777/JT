"""LLM-powered alert triage — reduce noise, prioritize threats.

Uses the Guardian One AI Engine to analyze alerts and provide:
- Severity assessment (confirm/adjust rule-assigned severity)
- Attack type classification
- Recommended response actions
- False positive probability

SAFETY: LLM output NEVER triggers destructive actions directly.
It only informs the triage result field on alerts.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from guardian_one.varys.models import Alert, AlertSeverity

if TYPE_CHECKING:
    from guardian_one.core.ai_engine import AIEngine

logger = logging.getLogger(__name__)

VARYS_SYSTEM_PROMPT = (
    "You are VARYS, a cybersecurity sentinel within Guardian One. "
    "You analyze security alerts and events to determine severity, "
    "identify likely attack patterns, and recommend response actions. "
    "Be precise, concise, and security-focused. "
    "Never downplay genuine threats. When uncertain, err on the side of caution. "
    "Output structured JSON when asked."
)

TRIAGE_PROMPT_TEMPLATE = """\
Analyze this security alert and provide a triage assessment.

Alert: {title}
Description: {description}
Severity (rule-assigned): {severity}
Rule: {rule_name} ({rule_id})
MITRE ATT&CK: {mitre_tactic} / {mitre_technique}
Source IP: {source_ip}
Source User: {source_user}
Host: {host_name}
Event Count: {event_count}

Event details:
{event_details}

Respond in JSON format:
{{
    "assessed_severity": "low|medium|high|critical",
    "confidence": 0.0-1.0,
    "attack_type": "brief description of likely attack",
    "false_positive_probability": 0.0-1.0,
    "recommended_actions": ["action1", "action2"],
    "summary": "1-2 sentence assessment"
}}
"""


class LLMTriage:
    """Use AI to triage and contextualize security alerts."""

    def __init__(self, ai_engine: AIEngine | None = None) -> None:
        self._ai = ai_engine
        self._total_triaged: int = 0

    def set_ai_engine(self, engine: AIEngine) -> None:
        self._ai = engine

    @property
    def is_available(self) -> bool:
        return self._ai is not None and self._ai.is_available()

    @property
    def total_triaged(self) -> int:
        return self._total_triaged

    def triage(self, alert: Alert) -> dict[str, Any]:
        """Run LLM triage on an alert.

        Returns the parsed triage result dict. Falls back to a
        deterministic assessment if AI is unavailable.
        """
        if not self.is_available:
            return self._deterministic_triage(alert)

        # Build event details summary
        event_details = []
        for i, evt in enumerate(alert.events[:10], 1):  # Cap at 10
            event_details.append(
                f"  {i}. [{evt.category}] {evt.action} "
                f"from={evt.source_ip or evt.source_user or 'unknown'} "
                f"host={evt.host_name or 'unknown'} "
                f"cmd={evt.process_command_line or 'N/A'}"
            )

        prompt = TRIAGE_PROMPT_TEMPLATE.format(
            title=alert.title,
            description=alert.description,
            severity=alert.severity.value,
            rule_name=alert.rule_name,
            rule_id=alert.rule_id,
            mitre_tactic=alert.mitre_tactic or "N/A",
            mitre_technique=alert.mitre_technique or "N/A",
            source_ip=alert.source_ip or "N/A",
            source_user=alert.source_user or "N/A",
            host_name=alert.host_name or "N/A",
            event_count=len(alert.events),
            event_details="\n".join(event_details) or "  (no event details)",
        )

        try:
            response = self._ai.reason_stateless(
                prompt=prompt,
                system=VARYS_SYSTEM_PROMPT,
                temperature=0.1,  # Very deterministic for security
                max_tokens=512,
            )

            if not response.success:
                return self._deterministic_triage(alert)

            # Parse JSON from response
            result = self._parse_json_response(response.content)
            if result:
                alert.triage_result = result.get("summary", "")
                alert.risk_score = 1.0 - result.get("false_positive_probability", 0.5)
                self._total_triaged += 1
                return result

        except Exception as exc:
            logger.error("LLM triage failed: %s", exc)

        return self._deterministic_triage(alert)

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, Any] | None:
        """Extract JSON from LLM response (handles markdown code blocks)."""
        text = content.strip()

        # Strip markdown code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
        return None

    @staticmethod
    def _deterministic_triage(alert: Alert) -> dict[str, Any]:
        """Fallback triage without AI — use rule severity directly."""
        severity_scores = {
            AlertSeverity.LOW: 0.2,
            AlertSeverity.MEDIUM: 0.5,
            AlertSeverity.HIGH: 0.75,
            AlertSeverity.CRITICAL: 0.95,
        }
        score = severity_scores.get(alert.severity, 0.5)

        actions = ["Log and monitor"]
        if alert.severity in (AlertSeverity.HIGH, AlertSeverity.CRITICAL):
            actions.append("Investigate immediately")
            if alert.source_ip:
                actions.append(f"Consider blocking {alert.source_ip}")

        result = {
            "assessed_severity": alert.severity.value,
            "confidence": 0.5,  # Lower confidence without AI
            "attack_type": alert.rule_name or "Unknown",
            "false_positive_probability": 1.0 - score,
            "recommended_actions": actions,
            "summary": f"[Deterministic] {alert.title} — severity {alert.severity.value}",
        }
        alert.triage_result = result["summary"]
        alert.risk_score = score
        return result
