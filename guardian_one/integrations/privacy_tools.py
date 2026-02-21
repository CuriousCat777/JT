"""Privacy tool integrations — NordVPN, DeleteMe, etc.

Providers auto-detect credentials from environment variables.
When credentials are absent they operate in offline mode.
"""

from __future__ import annotations

import abc
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VPNStatus:
    connected: bool
    server: str = ""
    country: str = ""
    protocol: str = ""
    ip_address: str = ""


@dataclass
class BrokerRemovalReport:
    """Report from a data broker removal service."""
    scan_date: str
    brokers_found: int
    brokers_removed: int
    pending_removals: int
    exposures: list[dict[str, Any]] = field(default_factory=list)


class VPNProvider(abc.ABC):
    @abc.abstractmethod
    def status(self) -> VPNStatus: ...

    @abc.abstractmethod
    def connect(self, country: str | None = None) -> bool: ...

    @abc.abstractmethod
    def disconnect(self) -> bool: ...

    @property
    @abc.abstractmethod
    def has_credentials(self) -> bool: ...

    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...


class DataBrokerService(abc.ABC):
    @abc.abstractmethod
    def latest_report(self) -> BrokerRemovalReport | None: ...

    @abc.abstractmethod
    def trigger_scan(self) -> bool: ...

    @property
    @abc.abstractmethod
    def has_credentials(self) -> bool: ...

    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...


class NordVPNProvider(VPNProvider):
    """NordVPN integration.

    Detects credentials via:
    1. ``NORDVPN_TOKEN`` env var (API access)
    2. Local NordVPN CLI (checks if ``nordvpn`` command is available)

    To activate:
    1. Install NordVPN CLI: https://nordvpn.com/download/linux/
    2. Run ``nordvpn login`` or set NORDVPN_TOKEN env var
    """

    def __init__(self) -> None:
        self._token = os.environ.get("NORDVPN_TOKEN", "")
        self._cli_available = self._check_cli()
        self._last_error: str = ""

    @property
    def provider_name(self) -> str:
        return "nordvpn"

    @property
    def has_credentials(self) -> bool:
        return bool(self._token) or self._cli_available

    @property
    def last_error(self) -> str:
        return self._last_error

    @staticmethod
    def _check_cli() -> bool:
        """Check if nordvpn CLI is installed."""
        try:
            result = subprocess.run(
                ["nordvpn", "version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def status(self) -> VPNStatus:
        if not self._cli_available:
            self._last_error = "NordVPN CLI not installed"
            return VPNStatus(connected=False)

        try:
            result = subprocess.run(
                ["nordvpn", "status"],
                capture_output=True, text=True, timeout=10,
            )
            output = result.stdout.lower()
            connected = "connected" in output and "disconnected" not in output

            server = ""
            country = ""
            protocol = ""
            ip_address = ""
            for line in result.stdout.splitlines():
                lower = line.lower().strip()
                if lower.startswith("server:"):
                    server = line.split(":", 1)[1].strip()
                elif lower.startswith("country:"):
                    country = line.split(":", 1)[1].strip()
                elif lower.startswith("current protocol:"):
                    protocol = line.split(":", 1)[1].strip()
                elif lower.startswith("your new ip:") or lower.startswith("ip:"):
                    ip_address = line.split(":", 1)[1].strip()

            return VPNStatus(
                connected=connected,
                server=server,
                country=country,
                protocol=protocol,
                ip_address=ip_address,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            self._last_error = f"Failed to get VPN status: {exc}"
            return VPNStatus(connected=False)

    def connect(self, country: str | None = None) -> bool:
        if not self._cli_available:
            self._last_error = "NordVPN CLI not installed"
            return False
        try:
            cmd = ["nordvpn", "connect"]
            if country:
                cmd.append(country)
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as exc:
            self._last_error = f"Failed to connect: {exc}"
            return False

    def disconnect(self) -> bool:
        if not self._cli_available:
            self._last_error = "NordVPN CLI not installed"
            return False
        try:
            result = subprocess.run(
                ["nordvpn", "disconnect"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as exc:
            self._last_error = f"Failed to disconnect: {exc}"
            return False

    def provider_status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "cli_available": self._cli_available,
            "token_set": bool(self._token),
            "last_error": self._last_error,
        }


class DeleteMeProvider(DataBrokerService):
    """DeleteMe data broker removal integration.

    Credentials lookup:
    1. ``api_key`` constructor arg
    2. ``DELETEME_API_KEY`` env var

    To activate:
    1. Subscribe to DeleteMe: https://joindeleteme.com
    2. Set DELETEME_API_KEY env var
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("DELETEME_API_KEY", "")
        self._base_url = os.environ.get(
            "DELETEME_BASE_URL", "https://api.joindeleteme.com"
        )
        self._last_error: str = ""

    @property
    def provider_name(self) -> str:
        return "deleteme"

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key)

    @property
    def last_error(self) -> str:
        return self._last_error

    def latest_report(self) -> BrokerRemovalReport | None:
        if not self.has_credentials:
            self._last_error = "Missing DELETEME_API_KEY env var."
            return None
        # Real: GET /api/v1/reports/latest with API key
        self._last_error = "API not yet implemented — key detected"
        return None

    def trigger_scan(self) -> bool:
        if not self.has_credentials:
            self._last_error = "Missing DELETEME_API_KEY env var."
            return False
        # Real: POST /api/v1/scans with API key
        self._last_error = "API not yet implemented — key detected"
        return False

    def provider_status(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "has_credentials": self.has_credentials,
            "base_url": self._base_url,
            "last_error": self._last_error,
        }
