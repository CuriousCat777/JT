"""H.O.M.E. L.I.N.K. Tailscale VPN Integration — Secure remote access.

Provides VPN-only external access to the sovereign IoT stack:
- Tailscale status monitoring (connected peers, exit nodes)
- MagicDNS hostname resolution
- ACL policy enforcement
- Connection health checks
- Remote access audit logging

Security model:
- VPN is the ONLY path for external access
- No port forwarding, no exposed services
- All remote connections logged and audited
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


@dataclass
class TailscalePeer:
    """A connected Tailscale peer/device."""
    hostname: str
    ip_address: str                  # Tailscale IP (100.x.y.z)
    os: str = ""
    is_online: bool = False
    is_exit_node: bool = False
    is_relay: bool = False           # Using DERP relay (not direct)
    last_seen: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hostname": self.hostname,
            "ip_address": self.ip_address,
            "os": self.os,
            "is_online": self.is_online,
            "is_exit_node": self.is_exit_node,
            "is_relay": self.is_relay,
            "last_seen": self.last_seen,
            "tags": self.tags,
        }


@dataclass
class TailscaleConfig:
    """Tailscale configuration."""
    enabled: bool = True
    accept_routes: bool = True       # Accept subnet routes from other nodes
    accept_dns: bool = True          # Use MagicDNS
    exit_node: str = ""              # Exit node hostname (empty = none)
    advertise_routes: list[str] = field(default_factory=list)  # Subnets to share


class TailscaleClient:
    """Tailscale VPN client wrapper.

    Monitors Tailscale daemon status and provides structured
    access to network peer information. All operations are
    read-only unless explicitly authorized.
    """

    def __init__(
        self,
        config: TailscaleConfig | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._config = config or TailscaleConfig()
        self._audit = audit
        self._peers: list[TailscalePeer] = []
        self._status_cache: dict[str, Any] = {}
        self._last_check: str = ""
        self._available = shutil.which("tailscale") is not None

    @property
    def available(self) -> bool:
        """Whether the tailscale CLI is installed."""
        return self._available

    def status(self) -> dict[str, Any]:
        """Get Tailscale daemon status.

        Calls `tailscale status --json` and parses the output.
        """
        if not self._available:
            return {
                "installed": False,
                "connected": False,
                "error": "tailscale CLI not found",
            }

        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return {
                    "installed": True,
                    "connected": False,
                    "error": result.stderr.strip(),
                }

            data = json.loads(result.stdout)
            self._status_cache = data
            self._last_check = datetime.now(timezone.utc).isoformat()
            self._parse_peers(data)

            return {
                "installed": True,
                "connected": data.get("BackendState") == "Running",
                "tailscale_ip": data.get("TailscaleIPs", [""])[0] if data.get("TailscaleIPs") else "",
                "hostname": data.get("Self", {}).get("HostName", ""),
                "os": data.get("Self", {}).get("OS", ""),
                "online_peers": len([p for p in self._peers if p.is_online]),
                "total_peers": len(self._peers),
                "magic_dns": data.get("MagicDNSSuffix", ""),
                "last_check": self._last_check,
            }

        except subprocess.TimeoutExpired:
            return {"installed": True, "connected": False, "error": "timeout"}
        except (json.JSONDecodeError, OSError) as exc:
            return {"installed": True, "connected": False, "error": str(exc)}

    def peers(self) -> list[TailscalePeer]:
        """Return list of known Tailscale peers."""
        if not self._peers:
            self.status()  # Refresh
        return list(self._peers)

    def online_peers(self) -> list[TailscalePeer]:
        """Return only online peers."""
        return [p for p in self.peers() if p.is_online]

    def _parse_peers(self, data: dict[str, Any]) -> None:
        """Parse peer information from tailscale status JSON."""
        self._peers.clear()
        peer_map = data.get("Peer", {})

        for _key, peer_data in peer_map.items():
            peer = TailscalePeer(
                hostname=peer_data.get("HostName", ""),
                ip_address=(
                    peer_data.get("TailscaleIPs", [""])[0]
                    if peer_data.get("TailscaleIPs") else ""
                ),
                os=peer_data.get("OS", ""),
                is_online=peer_data.get("Online", False),
                is_exit_node=peer_data.get("ExitNode", False),
                is_relay=peer_data.get("Relay", "") != "",
                last_seen=peer_data.get("LastSeen", ""),
                tags=peer_data.get("Tags", []),
            )
            self._peers.append(peer)

    def health_check(self) -> dict[str, Any]:
        """Run a health check on the Tailscale connection."""
        status = self.status()
        health: dict[str, Any] = {
            "healthy": status.get("connected", False),
            "issues": [],
        }

        if not status.get("installed"):
            health["issues"].append("Tailscale not installed")
            health["healthy"] = False
        elif not status.get("connected"):
            health["issues"].append("Tailscale not connected")
            health["healthy"] = False

        if status.get("connected"):
            online = status.get("online_peers", 0)
            if online == 0:
                health["issues"].append("No online peers")

            # Check for relay connections (slower, less private)
            relay_peers = [p for p in self._peers if p.is_relay and p.is_online]
            if relay_peers:
                health["issues"].append(
                    f"{len(relay_peers)} peer(s) using DERP relay (not direct)"
                )

        health["status"] = status
        self._log("tailscale_health_check", Severity.INFO, health)
        return health

    def summary_text(self) -> str:
        """Human-readable Tailscale status."""
        status = self.status()
        lines = [
            "",
            "  TAILSCALE VPN",
            "  " + "-" * 40,
            f"  Installed:  {'yes' if status.get('installed') else 'no'}",
            f"  Connected:  {'yes' if status.get('connected') else 'no'}",
        ]

        if status.get("connected"):
            lines.append(f"  IP:         {status.get('tailscale_ip', 'n/a')}")
            lines.append(f"  Hostname:   {status.get('hostname', 'n/a')}")
            lines.append(f"  MagicDNS:   {status.get('magic_dns', 'n/a')}")
            lines.append(f"  Peers:      {status.get('online_peers', 0)} online / "
                         f"{status.get('total_peers', 0)} total")

            online = self.online_peers()
            if online:
                lines.append("")
                lines.append("  ONLINE PEERS")
                for p in online:
                    relay = " (relay)" if p.is_relay else " (direct)"
                    exit_n = " [exit-node]" if p.is_exit_node else ""
                    lines.append(
                        f"    {p.hostname:<20} {p.ip_address:<16} "
                        f"{p.os}{relay}{exit_n}"
                    )

        lines.append("")
        return "\n".join(lines)

    def _log(self, action: str, severity: Severity, details: dict[str, Any]) -> None:
        if self._audit:
            self._audit.record(
                agent="tailscale",
                action=action,
                severity=severity,
                details=details,
            )
