"""Containment engine — host isolation and process control.

Safety: All containment actions are logged to audit and require
explicit rule triggers. LLM can recommend but never invoke directly.
"""

from __future__ import annotations

import logging
from typing import Any

from guardian_one.core.audit import AuditLog, Severity

log = logging.getLogger(__name__)


class ContainmentEngine:
    """Executes containment actions with full audit trail."""

    def __init__(self, audit: AuditLog) -> None:
        self._audit = audit
        self._isolated_hosts: set[str] = set()
        self._killed_processes: list[dict[str, Any]] = []

    @property
    def isolated_hosts(self) -> set[str]:
        return self._isolated_hosts.copy()

    def isolate_host(self, hostname: str) -> bool:
        """Isolate a host from the network.

        In production, this would call the Wazuh API or firewall rules.
        Currently logs the action for manual execution.
        """
        if not hostname:
            return False

        self._isolated_hosts.add(hostname)
        self._audit.record(
            agent="varys",
            action="host_isolated",
            severity=Severity.CRITICAL,
            details={"hostname": hostname},
            requires_review=True,
        )
        log.warning("HOST ISOLATED: %s (requires manual verification)", hostname)
        return True

    def release_host(self, hostname: str) -> bool:
        """Release a previously isolated host."""
        if hostname not in self._isolated_hosts:
            return False

        self._isolated_hosts.discard(hostname)
        self._audit.record(
            agent="varys",
            action="host_released",
            severity=Severity.WARNING,
            details={"hostname": hostname},
        )
        log.info("Host released: %s", hostname)
        return True

    def kill_process(self, hostname: str, pid: int, reason: str) -> bool:
        """Terminate a suspicious process.

        In production, this would send a kill command via Wazuh agent.
        """
        record = {
            "hostname": hostname,
            "pid": pid,
            "reason": reason,
        }
        self._killed_processes.append(record)
        self._audit.record(
            agent="varys",
            action="process_killed",
            severity=Severity.WARNING,
            details=record,
            requires_review=True,
        )
        log.warning("Process killed: PID %d on %s (%s)", pid, hostname, reason)
        return True
