"""Wazuh SIEM connector — pulls alerts from Wazuh Manager API.

Wazuh provides host-based intrusion detection, file integrity monitoring,
vulnerability scanning, and compliance checking. This connector pulls
alerts from the Wazuh API and normalizes them into SecurityEvent objects.

Requires:
- WAZUH_API_URL (e.g. https://wazuh-manager:55000)
- WAZUH_API_USER / WAZUH_API_PASSWORD
"""

from __future__ import annotations

import logging
import os
from typing import Any

from guardian_one.varys.ingestion.collector import BaseCollector
from guardian_one.varys.models import SecurityEvent

logger = logging.getLogger(__name__)


class WazuhConnector(BaseCollector):
    """Connect to Wazuh Manager API and pull security alerts."""

    def __init__(
        self,
        api_url: str = "",
        api_user: str = "",
        api_password: str = "",
        verify_ssl: bool = True,
    ) -> None:
        super().__init__("wazuh")
        self._api_url = (api_url or os.environ.get("WAZUH_API_URL", "")).rstrip("/")
        self._api_user = api_user or os.environ.get("WAZUH_API_USER", "")
        self._api_password = api_password or os.environ.get("WAZUH_API_PASSWORD", "")
        self._verify_ssl = verify_ssl
        self._token: str = ""
        self._last_alert_id: int = 0

    def is_available(self) -> bool:
        """Check if Wazuh credentials are configured."""
        return bool(self._api_url and self._api_user and self._api_password)

    def _authenticate(self) -> bool:
        """Authenticate with the Wazuh API and obtain a JWT token."""
        if not self.is_available():
            return False

        try:
            import httpx

            resp = httpx.post(
                f"{self._api_url}/security/user/authenticate",
                auth=(self._api_user, self._api_password),
                verify=self._verify_ssl,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data.get("data", {}).get("token", "")
            return bool(self._token)
        except Exception as exc:
            logger.error("Wazuh authentication failed: %s", exc)
            return False

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def collect(self) -> list[SecurityEvent]:
        """Pull new alerts from Wazuh and normalize them."""
        events: list[SecurityEvent] = []

        if not self.is_available():
            return events

        if not self._token and not self._authenticate():
            return events

        try:
            import httpx

            # Fetch alerts newer than last seen
            params: dict[str, Any] = {
                "limit": 100,
                "sort": "+id",
                "q": f"id>{self._last_alert_id}" if self._last_alert_id else "",
            }
            resp = httpx.get(
                f"{self._api_url}/alerts",
                headers=self._headers(),
                params={k: v for k, v in params.items() if v},
                verify=self._verify_ssl,
                timeout=30,
            )

            if resp.status_code == 401:
                # Token expired — re-authenticate once (no recursion)
                if self._authenticate():
                    resp = httpx.get(
                        f"{self._api_url}/alerts",
                        headers=self._headers(),
                        params={k: v for k, v in params.items() if v},
                        verify=self._verify_ssl,
                        timeout=30,
                    )
                    if resp.status_code != 200:
                        logger.error("Wazuh re-auth failed, status=%d", resp.status_code)
                        return events
                else:
                    return events

            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", {}).get("affected_items", [])

            for item in items:
                event = self._normalize_alert(item)
                if event:
                    events.append(event)
                    alert_id = item.get("id", 0)
                    if isinstance(alert_id, int) and alert_id > self._last_alert_id:
                        self._last_alert_id = alert_id

        except Exception as exc:
            logger.error("Wazuh alert fetch failed: %s", exc)

        self._events_collected += len(events)
        return events

    def _normalize_alert(self, alert: dict[str, Any]) -> SecurityEvent | None:
        """Convert a Wazuh alert into a normalized SecurityEvent."""
        rule = alert.get("rule", {})
        agent = alert.get("agent", {})
        data = alert.get("data", {})

        # Map Wazuh rule groups to ECS categories
        groups = rule.get("groups", [])
        category = self._map_category(groups)

        # Determine severity tag
        level = rule.get("level", 0)
        if level >= 12:
            severity = "critical"
        elif level >= 8:
            severity = "high"
        elif level >= 5:
            severity = "medium"
        else:
            severity = "low"

        return SecurityEvent(
            source="wazuh",
            category=category,
            action=rule.get("description", ""),
            outcome="failure" if level >= 5 else "unknown",
            source_ip=data.get("srcip", ""),
            source_user=data.get("srcuser", data.get("dstuser", "")),
            host_name=agent.get("name", ""),
            host_ip=agent.get("ip", ""),
            process_name=data.get("program_name", ""),
            file_path=data.get("file", ""),
            severity=severity,
            rule_id=str(rule.get("id", "")),
            raw=alert,
            tags=groups,
        )

    @staticmethod
    def _map_category(groups: list[str]) -> str:
        """Map Wazuh rule groups to ECS event categories."""
        group_set = set(groups)
        if group_set & {"authentication_failed", "authentication_success", "sshd", "pam"}:
            return "authentication"
        if group_set & {"syscheck", "fim"}:
            return "file"
        if group_set & {"firewall", "iptables"}:
            return "network"
        if group_set & {"rootcheck", "rootkit"}:
            return "malware"
        if group_set & {"ids", "suricata", "snort"}:
            return "intrusion_detection"
        if group_set & {"web", "apache", "nginx"}:
            return "web"
        return "configuration"

    def get_agent_status(self) -> dict[str, Any]:
        """Get status of all Wazuh agents."""
        if not self._token and not self._authenticate():
            return {"error": "authentication_failed"}

        try:
            import httpx

            resp = httpx.get(
                f"{self._api_url}/agents",
                headers=self._headers(),
                params={"limit": 50},
                verify=self._verify_ssl,
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("data", {})
        except Exception as exc:
            logger.error("Wazuh agent status failed: %s", exc)
            return {"error": str(exc)}
