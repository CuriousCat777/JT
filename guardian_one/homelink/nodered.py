"""H.O.M.E. L.I.N.K. Node-RED Integration — Visual automation flows.

Bridges Guardian One's automation engine with Node-RED for visual
flow-based IoT automation:
- Flow deployment and management via Node-RED Admin API
- MQTT node configuration for device communication
- Guardian One webhook nodes for AI-driven actions
- Flow status monitoring and health checks

All communication is LAN-local. Node-RED runs as a Docker container
on the sovereign host.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


@dataclass
class NodeRedFlow:
    """A Node-RED flow definition."""
    flow_id: str
    label: str
    disabled: bool = False
    nodes: list[dict[str, Any]] = field(default_factory=list)
    info: str = ""
    created: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.flow_id,
            "label": self.label,
            "disabled": self.disabled,
            "nodes": self.nodes,
            "info": self.info,
        }


@dataclass
class NodeRedConfig:
    """Configuration for Node-RED connection."""
    base_url: str = "http://localhost:1880"
    admin_auth_token: str = ""     # Bearer token for admin API
    timeout: int = 10


class NodeRedClient:
    """Node-RED Admin API client.

    Manages flows, monitors status, and configures MQTT/webhook
    nodes for Guardian One integration.
    """

    def __init__(
        self,
        config: NodeRedConfig | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._config = config or NodeRedConfig()
        self._audit = audit
        self._connected = False
        self._flows: dict[str, NodeRedFlow] = {}
        self._last_sync: str = ""

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def connect(self) -> bool:
        """Test connection to Node-RED admin API."""
        try:
            import urllib.request

            url = f"{self._config.base_url}/settings"
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._config.admin_auth_token:
                headers["Authorization"] = f"Bearer {self._config.admin_auth_token}"

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                data = json.loads(resp.read())
                self._connected = True
                self._log("nodered_connected", Severity.INFO, {
                    "version": data.get("httpNodeRoot", ""),
                })
                return True

        except Exception as exc:
            self._log("nodered_connect_error", Severity.WARNING, {
                "error": str(exc),
            })
            return False

    def disconnect(self) -> None:
        self._connected = False

    # ------------------------------------------------------------------
    # Flow management
    # ------------------------------------------------------------------

    def get_flows(self) -> list[NodeRedFlow]:
        """Fetch all flows from Node-RED."""
        data = self._api_get("/flows")
        if data is None:
            return list(self._flows.values())

        self._flows.clear()
        for item in data:
            if item.get("type") == "tab":
                flow = NodeRedFlow(
                    flow_id=item.get("id", ""),
                    label=item.get("label", ""),
                    disabled=item.get("disabled", False),
                    info=item.get("info", ""),
                )
                self._flows[flow.flow_id] = flow

        self._last_sync = datetime.now(timezone.utc).isoformat()
        return list(self._flows.values())

    def deploy_flow(self, flow: NodeRedFlow) -> bool:
        """Deploy a flow to Node-RED."""
        result = self._api_post("/flow", flow.to_dict())
        if result is not None:
            self._flows[flow.flow_id] = flow
            self._log("nodered_flow_deployed", Severity.INFO, {
                "flow_id": flow.flow_id,
                "label": flow.label,
            })
            return True
        return False

    def delete_flow(self, flow_id: str) -> bool:
        """Delete a flow from Node-RED."""
        result = self._api_delete(f"/flow/{flow_id}")
        if result:
            self._flows.pop(flow_id, None)
            self._log("nodered_flow_deleted", Severity.WARNING, {
                "flow_id": flow_id,
            })
            return True
        return False

    # ------------------------------------------------------------------
    # Guardian One integration flows
    # ------------------------------------------------------------------

    def create_guardian_flows(self) -> list[NodeRedFlow]:
        """Create the standard Guardian One integration flows.

        These flows bridge MQTT events with Guardian One's automation engine:
        1. Device state monitor — listens to homelink/devices/+/state
        2. Security alert flow — processes homelink/events/anomaly
        3. Automation trigger flow — fires on homelink/events/sentinel_scan
        """
        flows: list[NodeRedFlow] = []

        # 1. Device state monitor flow
        device_flow = NodeRedFlow(
            flow_id="guardian-device-monitor",
            label="Guardian One — Device Monitor",
            info="Monitors all device state changes via MQTT",
            nodes=[
                {
                    "id": "mqtt-device-in",
                    "type": "mqtt in",
                    "topic": "homelink/devices/+/state",
                    "qos": "1",
                    "name": "Device States",
                },
                {
                    "id": "device-parser",
                    "type": "json",
                    "name": "Parse JSON",
                },
                {
                    "id": "device-debug",
                    "type": "debug",
                    "name": "Device State Log",
                },
            ],
        )
        flows.append(device_flow)

        # 2. Security alert flow
        security_flow = NodeRedFlow(
            flow_id="guardian-security-alerts",
            label="Guardian One — Security Alerts",
            info="Processes network anomaly alerts from IoT Sentinel",
            nodes=[
                {
                    "id": "mqtt-anomaly-in",
                    "type": "mqtt in",
                    "topic": "homelink/events/anomaly",
                    "qos": "1",
                    "name": "Anomaly Events",
                },
                {
                    "id": "anomaly-parser",
                    "type": "json",
                    "name": "Parse Alert",
                },
                {
                    "id": "severity-switch",
                    "type": "switch",
                    "name": "Route by Severity",
                    "property": "payload.severity",
                    "rules": [
                        {"t": "eq", "v": "critical"},
                        {"t": "eq", "v": "warning"},
                        {"t": "eq", "v": "info"},
                    ],
                },
                {
                    "id": "critical-notify",
                    "type": "debug",
                    "name": "Critical Alert Handler",
                },
            ],
        )
        flows.append(security_flow)

        # 3. Automation trigger flow
        auto_flow = NodeRedFlow(
            flow_id="guardian-automation-triggers",
            label="Guardian One — Automation Triggers",
            info="Receives automation commands from Guardian One",
            nodes=[
                {
                    "id": "mqtt-command-in",
                    "type": "mqtt in",
                    "topic": "homelink/commands/#",
                    "qos": "1",
                    "name": "Commands",
                },
                {
                    "id": "command-parser",
                    "type": "json",
                    "name": "Parse Command",
                },
                {
                    "id": "command-exec",
                    "type": "function",
                    "name": "Execute Command",
                    "func": "// Route commands to appropriate handlers\nreturn msg;",
                },
            ],
        )
        flows.append(auto_flow)

        for f in flows:
            self._flows[f.flow_id] = f

        self._log("guardian_flows_created", Severity.INFO, {
            "flows": [f.flow_id for f in flows],
        })
        return flows

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Node-RED connection and flow status."""
        return {
            "connected": self._connected,
            "base_url": self._config.base_url,
            "flow_count": len(self._flows),
            "flows": [
                {"id": f.flow_id, "label": f.label, "disabled": f.disabled}
                for f in self._flows.values()
            ],
            "last_sync": self._last_sync,
        }

    def summary_text(self) -> str:
        """Human-readable Node-RED status."""
        lines = [
            "",
            "  NODE-RED AUTOMATION",
            "  " + "-" * 40,
            f"  Connected: {'yes' if self._connected else 'no'}",
            f"  URL:       {self._config.base_url}",
            f"  Flows:     {len(self._flows)}",
        ]
        for f in self._flows.values():
            status = "DISABLED" if f.disabled else "ACTIVE"
            lines.append(f"    [{status}] {f.label} ({f.flow_id})")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _api_get(self, path: str) -> Any | None:
        try:
            import urllib.request
            url = f"{self._config.base_url}{path}"
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._config.admin_auth_token:
                headers["Authorization"] = f"Bearer {self._config.admin_auth_token}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    def _api_post(self, path: str, data: dict[str, Any]) -> Any | None:
        try:
            import urllib.request
            url = f"{self._config.base_url}{path}"
            body = json.dumps(data).encode("utf-8")
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._config.admin_auth_token:
                headers["Authorization"] = f"Bearer {self._config.admin_auth_token}"
            req = urllib.request.Request(url, data=body, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    def _api_delete(self, path: str) -> bool:
        try:
            import urllib.request
            url = f"{self._config.base_url}{path}"
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if self._config.admin_auth_token:
                headers["Authorization"] = f"Bearer {self._config.admin_auth_token}"
            req = urllib.request.Request(url, method="DELETE", headers=headers)
            with urllib.request.urlopen(req, timeout=self._config.timeout) as resp:
                return resp.status < 400
        except Exception:
            return False

    def _log(self, action: str, severity: Severity, details: dict[str, Any]) -> None:
        if self._audit:
            self._audit.record(
                agent="node_red",
                action=action,
                severity=severity,
                details=details,
            )
