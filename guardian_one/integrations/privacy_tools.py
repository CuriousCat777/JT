"""Privacy tool integrations — stubs for NordVPN, DeleteMe, etc.

These provide monitoring and control interfaces for Jeremy's privacy stack.
"""

from __future__ import annotations

import abc
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


class DataBrokerService(abc.ABC):
    @abc.abstractmethod
    def latest_report(self) -> BrokerRemovalReport | None: ...

    @abc.abstractmethod
    def trigger_scan(self) -> bool: ...


class NordVPNProvider(VPNProvider):
    """NordVPN integration stub.

    To activate:
    1. Install NordVPN CLI on the host
    2. Authenticate via `nordvpn login`
    3. Or set NORDVPN_TOKEN env var for API access
    """

    def status(self) -> VPNStatus:
        # TODO: Parse output of `nordvpn status` CLI command
        return VPNStatus(connected=False)

    def connect(self, country: str | None = None) -> bool:
        # TODO: Run `nordvpn connect [country]`
        return False

    def disconnect(self) -> bool:
        # TODO: Run `nordvpn disconnect`
        return False


class DeleteMeProvider(DataBrokerService):
    """DeleteMe integration stub.

    To activate:
    1. Set DELETEME_API_KEY env var
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def latest_report(self) -> BrokerRemovalReport | None:
        # TODO: Call DeleteMe API for latest scan results
        return None

    def trigger_scan(self) -> bool:
        # TODO: Initiate a new scan via API
        return False
