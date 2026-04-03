"""Base collector and built-in log parsers for host-level ingestion.

Collectors normalize raw log data into SecurityEvent objects following
Elastic Common Schema conventions.
"""

from __future__ import annotations

import abc
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from guardian_one.varys.models import SecurityEvent

logger = logging.getLogger(__name__)


class BaseCollector(abc.ABC):
    """Abstract collector that ingestion sources must implement."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._events_collected: int = 0

    @abc.abstractmethod
    def collect(self) -> list[SecurityEvent]:
        """Collect and return normalized security events."""

    @property
    def events_collected(self) -> int:
        return self._events_collected


class AuthLogCollector(BaseCollector):
    """Parse /var/log/auth.log (Debian/Ubuntu) for authentication events.

    Detects:
    - Failed SSH logins
    - Successful SSH logins
    - sudo usage
    - User creation/modification
    """

    # sshd patterns
    _SSH_FAILED = re.compile(
        r"sshd\[\d+\]: Failed (\w+) for (?:invalid user )?(\S+) from (\S+) port (\d+)"
    )
    _SSH_ACCEPTED = re.compile(
        r"sshd\[\d+\]: Accepted (\w+) for (\S+) from (\S+) port (\d+)"
    )
    _SUDO = re.compile(
        r"sudo:\s+(\S+)\s+:.*COMMAND=(.*)"
    )
    _USERADD = re.compile(
        r"useradd\[\d+\]: new user: name=(\S+)"
    )

    def __init__(self, log_path: str = "/var/log/auth.log") -> None:
        super().__init__("auth_log")
        self._log_path = Path(log_path)
        self._last_position: int = 0

    def collect(self) -> list[SecurityEvent]:
        """Read new lines from auth.log and parse into events."""
        events: list[SecurityEvent] = []
        if not self._log_path.exists():
            return events

        try:
            with open(self._log_path) as f:
                f.seek(self._last_position)
                for line in f:
                    event = self._parse_line(line.strip())
                    if event:
                        events.append(event)
                self._last_position = f.tell()
        except PermissionError:
            logger.warning("Cannot read %s — need elevated permissions", self._log_path)
        except OSError as exc:
            logger.error("Error reading auth log: %s", exc)

        self._events_collected += len(events)
        return events

    def _parse_line(self, line: str) -> SecurityEvent | None:
        """Parse a single auth.log line into a SecurityEvent."""
        if not line:
            return None

        # Failed SSH login
        m = self._SSH_FAILED.search(line)
        if m:
            return SecurityEvent(
                source="auth_log",
                category="authentication",
                action="login_failed",
                outcome="failure",
                source_ip=m.group(3),
                source_user=m.group(2),
                destination_port=int(m.group(4)),
                raw={"line": line, "method": m.group(1)},
                tags=["ssh", "brute_force_candidate"],
            )

        # Successful SSH login
        m = self._SSH_ACCEPTED.search(line)
        if m:
            return SecurityEvent(
                source="auth_log",
                category="authentication",
                action="login_success",
                outcome="success",
                source_ip=m.group(3),
                source_user=m.group(2),
                destination_port=int(m.group(4)),
                raw={"line": line, "method": m.group(1)},
                tags=["ssh"],
            )

        # sudo command execution
        m = self._SUDO.search(line)
        if m:
            command = m.group(2).strip()
            tags = ["sudo"]
            # Flag dangerous commands
            if any(kw in command for kw in ("chmod 777", "rm -rf", "dd if=", "mkfs")):
                tags.append("dangerous_command")
            return SecurityEvent(
                source="auth_log",
                category="process",
                action="sudo_exec",
                outcome="success",
                source_user=m.group(1),
                process_command_line=command,
                raw={"line": line},
                tags=tags,
            )

        # User creation
        m = self._USERADD.search(line)
        if m:
            return SecurityEvent(
                source="auth_log",
                category="iam",
                action="user_created",
                outcome="success",
                source_user=m.group(1),
                raw={"line": line},
                tags=["user_management"],
            )

        return None

    def parse_line(self, line: str) -> SecurityEvent | None:
        """Public interface for parsing — delegates to internal parser."""
        return self._parse_line(line)


class SyslogCollector(BaseCollector):
    """Parse /var/log/syslog for system-level security events.

    Detects:
    - Service start/stop/restart
    - Kernel security events (firewall drops, segfaults)
    - Cron job executions
    """

    _IPTABLES_DROP = re.compile(
        r"kernel:.*(?:DROP|REJECT).*SRC=(\S+).*DST=(\S+).*DPT=(\d+)"
    )
    _SERVICE = re.compile(
        r"systemd\[\d+\]: (Started|Stopped|Reloading) (.+)\."
    )
    _SEGFAULT = re.compile(
        r"kernel:.*segfault at .* ip .* sp .* error .* in (\S+)"
    )
    _CRON = re.compile(
        r"CRON\[\d+\]: \((\S+)\) CMD \((.+)\)"
    )

    def __init__(self, log_path: str = "/var/log/syslog") -> None:
        super().__init__("syslog")
        self._log_path = Path(log_path)
        self._last_position: int = 0

    def collect(self) -> list[SecurityEvent]:
        events: list[SecurityEvent] = []
        if not self._log_path.exists():
            return events

        try:
            with open(self._log_path) as f:
                f.seek(self._last_position)
                for line in f:
                    event = self._parse_line(line.strip())
                    if event:
                        events.append(event)
                self._last_position = f.tell()
        except PermissionError:
            logger.warning("Cannot read %s — need elevated permissions", self._log_path)
        except OSError as exc:
            logger.error("Error reading syslog: %s", exc)

        self._events_collected += len(events)
        return events

    def _parse_line(self, line: str) -> SecurityEvent | None:
        if not line:
            return None

        # Firewall drop
        m = self._IPTABLES_DROP.search(line)
        if m:
            return SecurityEvent(
                source="syslog",
                category="network",
                action="firewall_drop",
                outcome="failure",
                source_ip=m.group(1),
                destination_ip=m.group(2),
                destination_port=int(m.group(3)),
                raw={"line": line},
                tags=["firewall", "blocked"],
            )

        # Service state change
        m = self._SERVICE.search(line)
        if m:
            action_map = {"Started": "service_start", "Stopped": "service_stop", "Reloading": "service_reload"}
            return SecurityEvent(
                source="syslog",
                category="configuration",
                action=action_map.get(m.group(1), "service_change"),
                outcome="success",
                process_name=m.group(2),
                raw={"line": line},
                tags=["service"],
            )

        # Segfault
        m = self._SEGFAULT.search(line)
        if m:
            return SecurityEvent(
                source="syslog",
                category="process",
                action="segfault",
                outcome="failure",
                process_name=m.group(1),
                raw={"line": line},
                tags=["crash", "potential_exploit"],
            )

        # Cron execution
        m = self._CRON.search(line)
        if m:
            return SecurityEvent(
                source="syslog",
                category="process",
                action="cron_exec",
                outcome="success",
                source_user=m.group(1),
                process_command_line=m.group(2),
                raw={"line": line},
                tags=["cron"],
            )

        return None

    def parse_line(self, line: str) -> SecurityEvent | None:
        return self._parse_line(line)
