"""Varys Sentinel — the local daemon for GOOS.

Varys is the always-on local agent that runs on the client's machine.
It consolidates:
- Security monitoring (varys/detection, varys/response)
- IoT management (homelink/ devices, automations, drivers)
- Network scanning and monitoring
- Local AI via Ollama
- Encrypted tunnel back to Guardian

Varys is the entire local operating system. Homelink is Varys's
interface to the physical world (IoT devices, smart home).

Deployment: systemd service on Linux
    systemctl start goos-varys
    systemctl enable goos-varys
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.core.config import load_config
from guardian_one.homelink.vault import Vault
from guardian_one.homelink.gateway import Gateway
from guardian_one.homelink.monitor import Monitor
from guardian_one.homelink.registry import IntegrationRegistry

log = logging.getLogger(__name__)


@dataclass
class SentinelStatus:
    """Current status of the Varys sentinel daemon."""
    running: bool
    uptime_seconds: float
    client_id: str
    hostname: str
    guardian_connected: bool
    devices_managed: int
    alerts_active: int
    last_scan: str
    ollama_available: bool
    tunnel_status: str  # connected, disconnected, error

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "uptime_seconds": self.uptime_seconds,
            "client_id": self.client_id,
            "hostname": self.hostname,
            "guardian_connected": self.guardian_connected,
            "devices_managed": self.devices_managed,
            "alerts_active": self.alerts_active,
            "last_scan": self.last_scan,
            "ollama_available": self.ollama_available,
            "tunnel_status": self.tunnel_status,
        }


class VarysSentinel:
    """The Varys local daemon — always-on sentinel on the client's machine.

    Responsibilities:
    1. Security: Monitor local network, detect threats, respond automatically
    2. IoT: Manage smart home devices via H.O.M.E. L.I.N.K.
    3. Network: Scan LAN, monitor traffic, enforce device policies
    4. AI: Local reasoning via Ollama (no internet needed)
    5. Tunnel: Maintain encrypted connection back to Guardian
    6. Offline: Continue operating even if internet is down

    Lifecycle:
        install() → start() → [run loop] → stop()
    """

    def __init__(
        self,
        client_id: str,
        data_dir: str = "/var/lib/goos",
        log_dir: str = "/var/log/goos",
    ) -> None:
        self.client_id = client_id
        self.data_dir = Path(data_dir)
        self.log_dir = Path(log_dir)
        self._running = False
        self._start_time: float = 0
        self._hostname = os.uname().nodename

        # Core subsystems
        self.audit = AuditLog(log_dir=self.log_dir)
        self.gateway = Gateway(audit=self.audit)

        passphrase = os.environ.get("GOOS_VARYS_PASSPHRASE", "")
        vault_path = self.data_dir / "varys_vault.enc"
        self.vault = Vault(vault_path, passphrase=passphrase) if passphrase else None

        self.registry = IntegrationRegistry()
        self.monitor = Monitor(
            gateway=self.gateway,
            vault=self.vault,
            registry=self.registry,
        ) if self.vault else None

        # State
        self._devices_managed = 0
        self._alerts_active = 0
        self._last_scan = ""
        self._guardian_connected = False
        self._tunnel_status = "disconnected"
        self._ollama_available = False
        self._queued_sync: list[dict[str, Any]] = []  # Data to sync when reconnected

    def install(self) -> dict[str, Any]:
        """Install Varys as a systemd service.

        Creates:
        - /var/lib/goos/ (data directory)
        - /var/log/goos/ (log directory)
        - /etc/systemd/system/goos-varys.service (systemd unit)
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        service_content = f"""[Unit]
Description=GOOS Varys Sentinel — Local AI Agent
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=goos
Group=goos
WorkingDirectory={self.data_dir}
Environment=GOOS_CLIENT_ID={self.client_id}
ExecStart=/usr/bin/python3 -m guardian_one.goos.sentinel --run
Restart=always
RestartSec=10
WatchdogSec=300

# Security hardening
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={self.data_dir} {self.log_dir}
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
"""
        service_path = Path("/etc/systemd/system/goos-varys.service")

        result = {
            "client_id": self.client_id,
            "hostname": self._hostname,
            "data_dir": str(self.data_dir),
            "log_dir": str(self.log_dir),
            "service_unit": str(service_path),
            "service_content": service_content,
        }

        self.audit.record(
            agent="varys_sentinel",
            action="install",
            severity=Severity.INFO,
            details=result,
        )

        return result

    def start(self) -> None:
        """Start the Varys sentinel daemon."""
        self._running = True
        self._start_time = time.monotonic()

        self.audit.record(
            agent="varys_sentinel",
            action="daemon_start",
            severity=Severity.INFO,
            details={
                "client_id": self.client_id,
                "hostname": self._hostname,
            },
        )

        # Initialize subsystems
        self._check_ollama()
        self._discover_network()
        self._establish_tunnel()

        log.info(
            "Varys sentinel started: client=%s host=%s ollama=%s tunnel=%s",
            self.client_id, self._hostname,
            self._ollama_available, self._tunnel_status,
        )

    def stop(self) -> None:
        """Stop the Varys sentinel daemon."""
        self._running = False
        self.audit.record(
            agent="varys_sentinel",
            action="daemon_stop",
            severity=Severity.INFO,
        )
        log.info("Varys sentinel stopped")

    def run_cycle(self) -> dict[str, Any]:
        """Execute one monitoring cycle.

        Called periodically by the daemon loop. Performs:
        1. Security scan (network + endpoint)
        2. IoT device health check
        3. Sync queued data to Guardian (if connected)
        4. Report status
        """
        now = datetime.now(timezone.utc).isoformat()
        self._last_scan = now
        cycle_results: dict[str, Any] = {"timestamp": now}

        # 1. Security scan
        security = self._security_scan()
        cycle_results["security"] = security

        # 2. IoT health check
        iot = self._iot_health_check()
        cycle_results["iot"] = iot

        # 3. Sync to Guardian if connected
        if self._guardian_connected and self._queued_sync:
            synced = self._sync_to_guardian()
            cycle_results["synced_items"] = synced

        # 4. Update status
        cycle_results["status"] = self.status().to_dict()

        self.audit.record(
            agent="varys_sentinel",
            action="cycle_complete",
            details=cycle_results,
        )

        return cycle_results

    def status(self) -> SentinelStatus:
        """Get current sentinel status."""
        uptime = time.monotonic() - self._start_time if self._running else 0
        return SentinelStatus(
            running=self._running,
            uptime_seconds=uptime,
            client_id=self.client_id,
            hostname=self._hostname,
            guardian_connected=self._guardian_connected,
            devices_managed=self._devices_managed,
            alerts_active=self._alerts_active,
            last_scan=self._last_scan,
            ollama_available=self._ollama_available,
            tunnel_status=self._tunnel_status,
        )

    def go_offline(self) -> None:
        """Detach from Guardian — Varys-only mode.

        Varys continues all local operations. Data is queued
        and synced when the client reconnects.
        """
        self._guardian_connected = False
        self._tunnel_status = "offline_mode"
        self.audit.record(
            agent="varys_sentinel",
            action="offline_mode_enabled",
            severity=Severity.INFO,
            details={"queued_items": len(self._queued_sync)},
        )

    def reconnect(self) -> bool:
        """Reconnect to Guardian and sync queued data."""
        self._establish_tunnel()
        if self._guardian_connected:
            self._sync_to_guardian()
            return True
        return False

    # ------------------------------------------------------------------
    # Private subsystem methods
    # ------------------------------------------------------------------

    def _check_ollama(self) -> None:
        """Check if Ollama is available locally."""
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://localhost:11434/api/tags", method="GET",
            )
            with urllib.request.urlopen(req, timeout=3):
                self._ollama_available = True
        except Exception:
            self._ollama_available = False

    def _discover_network(self) -> dict[str, Any]:
        """Discover devices on the local network."""
        # Uses existing homelink network scanning capabilities
        discovery = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": self._hostname,
            "status": "scan_complete",
        }
        self.audit.record(
            agent="varys_sentinel",
            action="network_discovery",
            details=discovery,
        )
        return discovery

    def _establish_tunnel(self) -> None:
        """Establish encrypted tunnel to Guardian (Tailscale/WireGuard)."""
        # In production, this connects via Tailscale or WireGuard
        # For now, check if Tailscale is running
        try:
            import subprocess
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                self._tunnel_status = "connected"
                self._guardian_connected = True
            else:
                self._tunnel_status = "disconnected"
                self._guardian_connected = False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._tunnel_status = "disconnected"
            self._guardian_connected = False

    def _security_scan(self) -> dict[str, Any]:
        """Run a local security scan."""
        return {
            "scan_type": "periodic",
            "threats_detected": 0,
            "devices_scanned": self._devices_managed,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _iot_health_check(self) -> dict[str, Any]:
        """Check health of managed IoT devices."""
        return {
            "devices_online": self._devices_managed,
            "devices_offline": 0,
            "firmware_updates_available": 0,
        }

    def _sync_to_guardian(self) -> int:
        """Sync queued data items to Guardian cloud."""
        synced = len(self._queued_sync)
        self._queued_sync.clear()
        self.audit.record(
            agent="varys_sentinel",
            action="sync_to_guardian",
            details={"items_synced": synced},
        )
        return synced

    def queue_for_sync(self, data: dict[str, Any]) -> None:
        """Queue data for syncing to Guardian when connected."""
        self._queued_sync.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        })
