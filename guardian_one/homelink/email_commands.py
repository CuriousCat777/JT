"""Email Command Processor for H.O.M.E. L.I.N.K.

Parses email subjects/bodies for device commands and executes them.
Commands are sent to jeremytabernero@gmail.com with subject prefix "HOMELINK:".

Supported commands (case-insensitive):
    HOMELINK: silence all
    HOMELINK: lights off
    HOMELINK: lights on
    HOMELINK: vacuum start
    HOMELINK: vacuum stop
    HOMELINK: <device-name> on
    HOMELINK: <device-name> off
    HOMELINK: <device-name> brightness <0-100>
    HOMELINK: tv mute
    HOMELINK: tv volume <0-100>
    HOMELINK: scene <scene-name>
    HOMELINK: wake
    HOMELINK: goodnight
    HOMELINK: status

Security:
- Only processes emails FROM the owner's verified addresses
- Commands are logged to the audit trail
- Rate limited to prevent abuse if account is compromised
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


# ---------------------------------------------------------------------------
# Command model
# ---------------------------------------------------------------------------

@dataclass
class EmailCommand:
    """Parsed email command."""
    raw_subject: str
    command: str          # normalized command string
    action: str           # 'on', 'off', 'brightness', 'mute', 'volume', etc.
    target: str           # device_id, 'all', 'scene', 'event', 'status'
    params: dict[str, Any] = field(default_factory=dict)
    sender: str = ""
    timestamp: str = ""
    message_id: str = ""


@dataclass
class CommandResult:
    """Result of executing an email command."""
    command: EmailCommand
    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Allowed senders — only process commands from these addresses
# ---------------------------------------------------------------------------

ALLOWED_SENDERS = {
    "jeremytabernero@gmail.com",
    # Add more trusted addresses here if needed
}


# ---------------------------------------------------------------------------
# Command parser
# ---------------------------------------------------------------------------

HOMELINK_PREFIX = re.compile(r"^HOMELINK\s*:\s*", re.IGNORECASE)

# Device name aliases → device_id mapping
DEVICE_ALIASES: dict[str, str] = {
    "tv": "lg-tv-65-living",
    "vacuum": "vacuum-roborock",
    "roborock": "vacuum-roborock",
    "front door": "cam-ring-front",
    "back door": "cam-ring-back",
    "manteca": "ring-doorbell-manteca",
    "echo living": "echo-dot-living",
    "echo bedroom": "echo-dot-bedroom",
    "hue bedroom": "light-hue-bedroom-01",
    "hue 1": "light-hue-bedroom-01",
    "hue 2": "light-hue-bedroom-02",
    "hue 3": "light-hue-bedroom-03",
    "govee lr": "light-govee-lr-main",
    "govee living": "light-govee-lr-main",
    "govee floor": "light-govee-lr-floor",
    "govee desk": "light-govee-desk",
    "govee balcony": "light-govee-balcony",
    "govee music": "light-govee-music-sync",
    "balcony": "light-govee-balcony",
    "desk": "light-govee-desk",
    "blinds": "blind-ryse-01",
    "blind": "blind-ryse-01",
}

# Scene aliases
SCENE_ALIASES: dict[str, str] = {
    "movie": "movie-night",
    "work": "work-mode",
    "away": "away",
    "goodnight": "goodnight",
    "gaming": "gaming",
    "relax": "relax",
}


def parse_email_command(subject: str, sender: str = "",
                        message_id: str = "") -> EmailCommand | None:
    """Parse an email subject line into an EmailCommand.

    Returns None if the subject doesn't start with 'HOMELINK:'.
    """
    match = HOMELINK_PREFIX.match(subject.strip())
    if not match:
        return None

    body = subject[match.end():].strip().lower()

    # -- Silence all --
    if body in ("silence all", "silence", "mute all", "shut up"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="silence_all", target="all",
            sender=sender, message_id=message_id,
        )

    # -- All lights --
    if body in ("lights off", "all lights off"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="off", target="all_lights",
            sender=sender, message_id=message_id,
        )
    if body in ("lights on", "all lights on"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="on", target="all_lights",
            sender=sender, message_id=message_id,
        )

    # -- Schedule events --
    if body in ("wake", "wake up", "good morning", "morning"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="event", target="wake",
            sender=sender, message_id=message_id,
        )
    if body in ("goodnight", "good night", "sleep", "bedtime"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="event", target="sleep",
            sender=sender, message_id=message_id,
        )
    if body in ("leaving", "leave", "away", "bye"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="event", target="leave",
            sender=sender, message_id=message_id,
        )
    if body in ("home", "arrive", "im home", "i'm home"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="event", target="arrive",
            sender=sender, message_id=message_id,
        )

    # -- Scene activation --
    scene_match = re.match(r"scene\s+(\w+)", body)
    if scene_match:
        scene_name = scene_match.group(1)
        scene_id = SCENE_ALIASES.get(scene_name, scene_name)
        return EmailCommand(
            raw_subject=subject, command=body,
            action="scene", target=scene_id,
            sender=sender, message_id=message_id,
        )

    # -- TV specific --
    if body in ("tv mute", "mute tv"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="mute", target="lg-tv-65-living",
            sender=sender, message_id=message_id,
        )
    tv_vol = re.match(r"tv\s+volume\s+(\d+)", body)
    if tv_vol:
        return EmailCommand(
            raw_subject=subject, command=body,
            action="volume", target="lg-tv-65-living",
            params={"volume": int(tv_vol.group(1))},
            sender=sender, message_id=message_id,
        )

    # -- Vacuum --
    if body in ("vacuum start", "vacuum", "vacuum clean", "clean"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="on", target="vacuum-roborock",
            sender=sender, message_id=message_id,
        )
    if body in ("vacuum stop", "vacuum dock", "dock"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="off", target="vacuum-roborock",
            sender=sender, message_id=message_id,
        )

    # -- Status request --
    if body in ("status", "report", "check"):
        return EmailCommand(
            raw_subject=subject, command=body,
            action="status", target="system",
            sender=sender, message_id=message_id,
        )

    # -- Generic device commands --
    # "<device> on/off"
    dev_onoff = re.match(r"(.+?)\s+(on|off)$", body)
    if dev_onoff:
        device_name = dev_onoff.group(1).strip()
        action = dev_onoff.group(2)
        device_id = DEVICE_ALIASES.get(device_name, device_name)
        return EmailCommand(
            raw_subject=subject, command=body,
            action=action, target=device_id,
            sender=sender, message_id=message_id,
        )

    # "<device> brightness <pct>"
    dev_bri = re.match(r"(.+?)\s+brightness\s+(\d+)", body)
    if dev_bri:
        device_name = dev_bri.group(1).strip()
        device_id = DEVICE_ALIASES.get(device_name, device_name)
        return EmailCommand(
            raw_subject=subject, command=body,
            action="brightness", target=device_id,
            params={"brightness": int(dev_bri.group(2))},
            sender=sender, message_id=message_id,
        )

    return None


# ---------------------------------------------------------------------------
# Command executor
# ---------------------------------------------------------------------------

class EmailCommandProcessor:
    """Processes parsed email commands by routing to device drivers.

    Usage:
        processor = EmailCommandProcessor(device_agent=agent, audit=audit)
        result = processor.execute(command)
    """

    # Rate limit: max commands per minute
    MAX_COMMANDS_PER_MINUTE = 10

    def __init__(self, device_agent, audit: AuditLog) -> None:
        self._agent = device_agent
        self._audit = audit
        self._command_log: list[float] = []

    def _rate_check(self) -> bool:
        """Return True if within rate limit."""
        now = time.time()
        self._command_log = [t for t in self._command_log if now - t < 60]
        if len(self._command_log) >= self.MAX_COMMANDS_PER_MINUTE:
            return False
        self._command_log.append(now)
        return True

    def _check_sender(self, cmd: EmailCommand) -> bool:
        """Verify the sender is authorized."""
        if not cmd.sender:
            return False
        # Extract email from "Name <email>" format
        email = cmd.sender
        if "<" in email:
            email = email.split("<")[1].rstrip(">")
        return email.lower().strip() in ALLOWED_SENDERS

    def execute(self, cmd: EmailCommand) -> CommandResult:
        """Execute a parsed email command."""
        # Security checks
        if not self._check_sender(cmd):
            self._audit.record(
                agent="homelink_email", action="COMMAND_REJECTED",
                severity=Severity.WARNING,
                details={"reason": "unauthorized_sender", "sender": cmd.sender,
                         "command": cmd.command},
            )
            return CommandResult(
                command=cmd, success=False,
                message=f"Unauthorized sender: {cmd.sender}",
            )

        if not self._rate_check():
            self._audit.record(
                agent="homelink_email", action="COMMAND_RATE_LIMITED",
                severity=Severity.WARNING,
                details={"sender": cmd.sender, "command": cmd.command},
            )
            return CommandResult(
                command=cmd, success=False,
                message="Rate limited — too many commands per minute",
            )

        # Log the command
        self._audit.record(
            agent="homelink_email", action="COMMAND_RECEIVED",
            severity=Severity.INFO,
            details={"sender": cmd.sender, "command": cmd.command,
                     "action": cmd.action, "target": cmd.target},
        )

        # Route to handler
        try:
            result = self._dispatch(cmd)
            self._audit.record(
                agent="homelink_email", action="COMMAND_EXECUTED",
                severity=Severity.INFO,
                details={"command": cmd.command, "success": result.success,
                         "message": result.message},
            )
            return result
        except Exception as exc:
            return CommandResult(
                command=cmd, success=False,
                message=f"Execution error: {exc}",
            )

    def _dispatch(self, cmd: EmailCommand) -> CommandResult:
        """Route command to the appropriate handler."""
        if cmd.action == "silence_all":
            return self._silence_all(cmd)
        elif cmd.action == "event":
            return self._fire_event(cmd)
        elif cmd.action == "scene":
            return self._activate_scene(cmd)
        elif cmd.action == "status":
            return self._get_status(cmd)
        elif cmd.action in ("on", "off"):
            if cmd.target == "all_lights":
                return self._all_lights(cmd)
            return self._device_power(cmd)
        elif cmd.action == "brightness":
            return self._device_brightness(cmd)
        elif cmd.action == "mute":
            return self._device_mute(cmd)
        elif cmd.action == "volume":
            return self._device_volume(cmd)
        else:
            return CommandResult(
                command=cmd, success=False,
                message=f"Unknown action: {cmd.action}",
            )

    def _silence_all(self, cmd: EmailCommand) -> CommandResult:
        """Mute TV + kill power to audio devices."""
        results = []
        registry = self._agent.device_registry
        from guardian_one.homelink.drivers import DriverFactory
        factory = DriverFactory(vault_retrieve=self._agent.drivers._vault_retrieve)

        for d in registry.all_devices():
            if d.category.value == "smart_tv" and d.ip_address:
                try:
                    driver = factory.get_lg_driver(d.ip_address)
                    r = driver.mute(True)
                    results.append(f"{d.name}: muted")
                except Exception:
                    results.append(f"{d.name}: mute failed")

            if d.category.value == "media_player" and d.ip_address:
                try:
                    driver = factory.get_kasa_driver(d.ip_address)
                    r = driver.turn_off()
                    results.append(f"{d.name}: power killed")
                except Exception:
                    results.append(f"{d.name}: kill failed")

        return CommandResult(
            command=cmd, success=True,
            message=f"Silenced {len(results)} devices",
            details={"results": results},
        )

    def _fire_event(self, cmd: EmailCommand) -> CommandResult:
        """Fire a schedule event (wake/sleep/leave/arrive)."""
        event = cmd.target
        results = self._agent.handle_schedule_event(event)
        return CommandResult(
            command=cmd, success=True,
            message=f"Event '{event}': {len(results)} actions executed",
            details={"results": results},
        )

    def _activate_scene(self, cmd: EmailCommand) -> CommandResult:
        """Activate a scene by ID."""
        results = self._agent.activate_scene(cmd.target)
        return CommandResult(
            command=cmd, success=True,
            message=f"Scene '{cmd.target}': {len(results)} actions",
            details={"results": results},
        )

    def _all_lights(self, cmd: EmailCommand) -> CommandResult:
        """Turn all lights on or off."""
        registry = self._agent.device_registry
        count = 0
        for d in registry.all_devices():
            if d.category.value == "smart_light":
                driver = self._agent.drivers.for_device(d)
                if driver:
                    if cmd.action == "on":
                        driver.turn_on()
                    else:
                        driver.turn_off()
                    count += 1
        return CommandResult(
            command=cmd, success=True,
            message=f"All lights {cmd.action}: {count} devices",
        )

    def _device_power(self, cmd: EmailCommand) -> CommandResult:
        """Turn a specific device on or off."""
        device = self._agent.get_device(cmd.target)
        if not device:
            return CommandResult(
                command=cmd, success=False,
                message=f"Device not found: {cmd.target}",
            )
        driver = self._agent.drivers.for_device(device)
        if not driver:
            return CommandResult(
                command=cmd, success=False,
                message=f"No driver for {cmd.target} (no IP or unsupported)",
            )
        if cmd.action == "on":
            result = driver.turn_on()
        else:
            result = driver.turn_off()
        return CommandResult(
            command=cmd, success=result.get("success", False),
            message=f"{device.name} {cmd.action}: {'OK' if result.get('success') else result.get('error', 'failed')}",
            details=result,
        )

    def _device_brightness(self, cmd: EmailCommand) -> CommandResult:
        """Set device brightness."""
        device = self._agent.get_device(cmd.target)
        if not device:
            return CommandResult(command=cmd, success=False,
                                message=f"Device not found: {cmd.target}")
        driver = self._agent.drivers.for_device(device)
        if not driver or not hasattr(driver, "set_brightness"):
            return CommandResult(command=cmd, success=False,
                                message=f"Brightness not supported: {cmd.target}")
        pct = cmd.params.get("brightness", 50)
        result = driver.set_brightness(pct)
        return CommandResult(
            command=cmd, success=result.get("success", False),
            message=f"{device.name} brightness {pct}%",
            details=result,
        )

    def _device_mute(self, cmd: EmailCommand) -> CommandResult:
        """Mute a device (TV)."""
        device = self._agent.get_device(cmd.target)
        if not device or not device.ip_address:
            return CommandResult(command=cmd, success=False,
                                message=f"Device not found or no IP: {cmd.target}")
        from guardian_one.homelink.drivers import DriverFactory
        factory = DriverFactory(vault_retrieve=self._agent.drivers._vault_retrieve)
        driver = factory.get_lg_driver(device.ip_address)
        result = driver.mute(True)
        return CommandResult(
            command=cmd, success=result.get("success", False),
            message=f"{device.name} muted",
            details=result,
        )

    def _device_volume(self, cmd: EmailCommand) -> CommandResult:
        """Set device volume (TV)."""
        device = self._agent.get_device(cmd.target)
        if not device or not device.ip_address:
            return CommandResult(command=cmd, success=False,
                                message=f"Device not found or no IP: {cmd.target}")
        from guardian_one.homelink.drivers import DriverFactory
        factory = DriverFactory(vault_retrieve=self._agent.drivers._vault_retrieve)
        driver = factory.get_lg_driver(device.ip_address)
        level = cmd.params.get("volume", 20)
        result = driver.set_volume(level)
        return CommandResult(
            command=cmd, success=result.get("success", False),
            message=f"{device.name} volume → {level}",
            details=result,
        )

    def _get_status(self, cmd: EmailCommand) -> CommandResult:
        """Build a status summary for email reply."""
        registry = self._agent.device_registry
        devices = registry.all_devices()
        total = len(devices)
        with_ip = len([d for d in devices if d.ip_address])
        lights = len([d for d in devices if d.category.value == "smart_light"])
        plugs = len([d for d in devices if d.category.value == "smart_plug"])

        summary = (
            f"H.O.M.E. L.I.N.K. Status\n"
            f"Devices: {total} total, {with_ip} reachable\n"
            f"Lights: {lights} | Plugs: {plugs}\n"
            f"Dashboard: http://localhost:5000/homelink"
        )
        return CommandResult(
            command=cmd, success=True, message=summary,
            details={"total": total, "reachable": with_ip,
                     "lights": lights, "plugs": plugs},
        )
