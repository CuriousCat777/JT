"""Auth log collector — ingests authentication events.

Supports local auth logs, and extensible to Okta/Azure AD.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class AuthLogCollector:
    """Collects authentication events from configured sources."""

    def __init__(self) -> None:
        self._sources: list[str] = []

    def add_source(self, source: str) -> None:
        """Register an auth log source (e.g., 'local', 'okta', 'azure_ad')."""
        self._sources.append(source)

    def collect(self) -> list[dict[str, Any]]:
        """Collect events from all registered sources.

        Returns a list of normalized event dicts with keys:
            user, source_ip, hour, hostname, event_type, user_agent, timestamp
        """
        events: list[dict[str, Any]] = []
        for source in self._sources:
            events.extend(self._collect_from(source))
        return events

    def _collect_from(self, source: str) -> list[dict[str, Any]]:
        """Collect from a single source. Override per-source."""
        if source == "local":
            return self._collect_local()
        log.debug("Source %s not yet implemented", source)
        return []

    def _collect_local(self) -> list[dict[str, Any]]:
        """Read local auth.log (Linux) or equivalent.

        Returns empty list if not available (e.g., in CI/testing).
        """
        # Placeholder — production would parse /var/log/auth.log
        return []
