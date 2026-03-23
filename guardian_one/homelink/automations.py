"""H.O.M.E. L.I.N.K. Automation Engine — schedule-driven, room-based device control.

Connects Chronos (schedule agent) to DeviceAgent actions:
- Wake routine: open blinds, turn on lights, start coffee plug
- Sleep routine: close blinds, dim lights, arm cameras
- Leave routine: close blinds, turn off plugs, arm security
- Arrive routine: open blinds, turn on lights, disarm entry

Automation rules are policy-driven and audited through Guardian One.
All actions are reversible and logged. No action executes without
matching a defined rule in the automation registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from guardian_one.core.audit import AuditLog, Severity


# ---------------------------------------------------------------------------
# Automation model
# ---------------------------------------------------------------------------

class TriggerType(Enum):
    """What initiates an automation."""
    SCHEDULE = "schedule"           # Time-based (via Chronos)
    OCCUPANCY = "occupancy"         # Motion detected / cleared
    SUNRISE = "sunrise"             # Solar event
    SUNSET = "sunset"               # Solar event
    DEVICE_STATE = "device_state"   # Device reports a state change
    MANUAL = "manual"               # User-initiated
    SYSTEM_EVENT = "system_event"   # Guardian One lifecycle event


class ActionType(Enum):
    """What the automation does."""
    DEVICE_ON = "device_on"
    DEVICE_OFF = "device_off"
    BLIND_OPEN = "blind_open"
    BLIND_CLOSE = "blind_close"
    BLIND_POSITION = "blind_position"   # Set to specific %
    LIGHT_ON = "light_on"
    LIGHT_OFF = "light_off"
    LIGHT_DIM = "light_dim"             # Set brightness %
    LIGHT_COLOR = "light_color"         # Set color (Hue/Govee)
    CAMERA_ARM = "camera_arm"
    CAMERA_DISARM = "camera_disarm"
    NOTIFY = "notify"                   # Send notification
    SCENE_ACTIVATE = "scene_activate"   # Activate a named scene


class AutomationStatus(Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    PAUSED = "paused"       # Temporarily paused (e.g., vacation mode)


@dataclass
class AutomationAction:
    """A single action within an automation rule."""
    action_type: ActionType
    target_device_id: str = ""     # Device to act on (empty for notify/scene)
    target_room_id: str = ""       # Room to act on (applies to all room devices)
    parameters: dict[str, Any] = field(default_factory=dict)
    delay_seconds: int = 0         # Delay before executing this action


@dataclass
class AutomationRule:
    """A policy-driven automation rule.

    Rules are the core of H.O.M.E. L.I.N.K. automation:
    - Each rule has a trigger condition and one or more actions
    - Rules are scoped to rooms or specific devices
    - All executions are audit-logged
    - Rules can be enabled/disabled/paused independently
    """
    rule_id: str
    name: str
    description: str
    trigger_type: TriggerType
    trigger_config: dict[str, Any] = field(default_factory=dict)
    actions: list[AutomationAction] = field(default_factory=list)
    room_id: str = ""              # Scope to a room (empty = global)
    status: AutomationStatus = AutomationStatus.ENABLED
    priority: int = 5              # 1 = highest, 10 = lowest
    tags: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_executed: str = ""
    execution_count: int = 0


# ---------------------------------------------------------------------------
# Scene model — named device state presets
# ---------------------------------------------------------------------------

@dataclass
class Scene:
    """A named preset of device states that can be activated at once."""
    scene_id: str
    name: str
    description: str
    actions: list[AutomationAction] = field(default_factory=list)
    room_id: str = ""              # Scope to room (empty = house-wide)
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Automation engine
# ---------------------------------------------------------------------------

class AutomationEngine:
    """Manages and evaluates automation rules for the home.

    The engine does NOT directly control devices — it evaluates rules and
    produces a list of actions that the DeviceAgent should execute.
    This separation ensures all actions are auditable and reversible.
    """

    def __init__(self, audit: AuditLog | None = None) -> None:
        self._rules: dict[str, AutomationRule] = {}
        self._scenes: dict[str, Scene] = {}
        self._execution_log: list[dict[str, Any]] = []
        self._audit = audit

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, rule: AutomationRule) -> None:
        self._rules[rule.rule_id] = rule

    def get_rule(self, rule_id: str) -> AutomationRule | None:
        return self._rules.get(rule_id)

    def remove_rule(self, rule_id: str) -> bool:
        return self._rules.pop(rule_id, None) is not None

    def all_rules(self) -> list[AutomationRule]:
        return list(self._rules.values())

    def enabled_rules(self) -> list[AutomationRule]:
        return [r for r in self._rules.values()
                if r.status == AutomationStatus.ENABLED]

    def rules_by_trigger(self, trigger_type: TriggerType) -> list[AutomationRule]:
        return [r for r in self._rules.values()
                if r.trigger_type == trigger_type
                and r.status == AutomationStatus.ENABLED]

    def rules_for_room(self, room_id: str) -> list[AutomationRule]:
        return [r for r in self._rules.values()
                if r.room_id == room_id]

    def enable_rule(self, rule_id: str) -> bool:
        rule = self._rules.get(rule_id)
        if rule:
            rule.status = AutomationStatus.ENABLED
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        rule = self._rules.get(rule_id)
        if rule:
            rule.status = AutomationStatus.DISABLED
            return True
        return False

    # ------------------------------------------------------------------
    # Scene management
    # ------------------------------------------------------------------

    def add_scene(self, scene: Scene) -> None:
        self._scenes[scene.scene_id] = scene

    def get_scene(self, scene_id: str) -> Scene | None:
        return self._scenes.get(scene_id)

    def all_scenes(self) -> list[Scene]:
        return list(self._scenes.values())

    def activate_scene(self, scene_id: str) -> list[AutomationAction]:
        """Return actions for a scene activation (DeviceAgent executes them)."""
        scene = self._scenes.get(scene_id)
        if not scene:
            return []
        now = datetime.now(timezone.utc).isoformat()
        self._execution_log.append({
            "type": "scene",
            "scene_id": scene_id,
            "name": scene.name,
            "action_count": len(scene.actions),
            "timestamp": now,
        })
        if self._audit:
            self._audit.record(
                agent="device_agent",
                action=f"scene_activated:{scene_id}",
                severity=Severity.INFO,
                details={"name": scene.name, "actions": len(scene.actions)},
            )
        return list(scene.actions)

    # ------------------------------------------------------------------
    # Rule evaluation — called by DeviceAgent on events
    # ------------------------------------------------------------------

    def evaluate_trigger(
        self,
        trigger_type: TriggerType,
        context: dict[str, Any] | None = None,
    ) -> list[AutomationAction]:
        """Evaluate all rules matching a trigger and return pending actions.

        This is the main entry point for automation:
        1. Chronos fires a schedule event (wake, sleep, leave, arrive)
        2. DeviceAgent calls evaluate_trigger(SCHEDULE, {"event": "wake"})
        3. Engine returns list of actions to execute
        4. DeviceAgent executes each action and logs to audit

        Args:
            trigger_type: What type of event occurred
            context: Additional data (time, event name, device state, etc.)

        Returns:
            Ordered list of actions to execute
        """
        context = context or {}
        matching_rules = self.rules_by_trigger(trigger_type)
        now = datetime.now(timezone.utc).isoformat()
        all_actions: list[AutomationAction] = []

        # Sort by priority (1 = highest)
        matching_rules.sort(key=lambda r: r.priority)

        for rule in matching_rules:
            if self._rule_matches_context(rule, context):
                all_actions.extend(rule.actions)
                rule.last_executed = now
                rule.execution_count += 1
                self._execution_log.append({
                    "type": "rule",
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "trigger": trigger_type.value,
                    "context": context,
                    "action_count": len(rule.actions),
                    "timestamp": now,
                })
                if self._audit:
                    self._audit.record(
                        agent="device_agent",
                        action=f"automation_fired:{rule.rule_id}",
                        severity=Severity.INFO,
                        details={
                            "name": rule.name,
                            "trigger": trigger_type.value,
                            "actions": len(rule.actions),
                        },
                    )

        return all_actions

    def _rule_matches_context(
        self, rule: AutomationRule, context: dict[str, Any]
    ) -> bool:
        """Check if a rule's trigger_config matches the event context."""
        cfg = rule.trigger_config
        if not cfg:
            return True  # No config = always matches this trigger type

        # Schedule trigger: match on event name (wake, sleep, leave, arrive)
        if rule.trigger_type == TriggerType.SCHEDULE:
            if "event" in cfg and cfg["event"] != context.get("event"):
                return False
            if "time" in cfg and cfg["time"] != context.get("time"):
                return False

        # Occupancy trigger: match on state (detected, cleared)
        if rule.trigger_type == TriggerType.OCCUPANCY:
            if "state" in cfg and cfg["state"] != context.get("state"):
                return False

        # Device state trigger: match on device_id and state
        if rule.trigger_type == TriggerType.DEVICE_STATE:
            if "device_id" in cfg and cfg["device_id"] != context.get("device_id"):
                return False
            if "state" in cfg and cfg["state"] != context.get("state"):
                return False

        return True

    # ------------------------------------------------------------------
    # Execution log
    # ------------------------------------------------------------------

    def execution_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(reversed(self._execution_log[-limit:]))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        return {
            "total_rules": len(self._rules),
            "enabled_rules": len(self.enabled_rules()),
            "total_scenes": len(self._scenes),
            "total_executions": len(self._execution_log),
            "rules_by_trigger": {
                t.value: len(self.rules_by_trigger(t))
                for t in TriggerType
            },
        }

    # ------------------------------------------------------------------
    # Load default automations
    # ------------------------------------------------------------------

    def load_defaults(self) -> None:
        """Load Jeremy's default automation rules and scenes."""
        for rule in _default_rules():
            self.add_rule(rule)
        for scene in _default_scenes():
            self.add_scene(scene)


# ---------------------------------------------------------------------------
# Jeremy's default automation rules
# ---------------------------------------------------------------------------

def _default_rules() -> list[AutomationRule]:
    """Chronos-driven automations for Jeremy's daily routines."""
    return [
        # --- Morning / Wake ---
        AutomationRule(
            rule_id="auto-wake-blinds",
            name="Morning — Open Blinds",
            description="Open Ryse blinds when Chronos fires wake event",
            trigger_type=TriggerType.SCHEDULE,
            trigger_config={"event": "wake"},
            actions=[
                AutomationAction(
                    action_type=ActionType.BLIND_OPEN,
                    target_device_id="blind-ryse-01",
                ),
            ],
            room_id="living-room",
            priority=1,
            tags=["morning", "chronos", "blinds"],
        ),
        AutomationRule(
            rule_id="auto-wake-lights",
            name="Morning — Lights On",
            description="Turn on living room lights at wake time",
            trigger_type=TriggerType.SCHEDULE,
            trigger_config={"event": "wake"},
            actions=[
                AutomationAction(
                    action_type=ActionType.LIGHT_ON,
                    target_room_id="living-room",
                    parameters={"brightness": 80},
                ),
            ],
            room_id="living-room",
            priority=2,
            tags=["morning", "chronos", "lights"],
        ),

        # --- Evening / Sleep ---
        AutomationRule(
            rule_id="auto-sleep-blinds",
            name="Night — Close Blinds",
            description="Close all blinds when Chronos fires sleep event",
            trigger_type=TriggerType.SCHEDULE,
            trigger_config={"event": "sleep"},
            actions=[
                AutomationAction(
                    action_type=ActionType.BLIND_CLOSE,
                    target_device_id="blind-ryse-01",
                ),
            ],
            room_id="living-room",
            priority=1,
            tags=["night", "chronos", "blinds"],
        ),
        AutomationRule(
            rule_id="auto-sleep-lights",
            name="Night — Lights Off",
            description="Turn off all lights when going to sleep",
            trigger_type=TriggerType.SCHEDULE,
            trigger_config={"event": "sleep"},
            actions=[
                AutomationAction(
                    action_type=ActionType.LIGHT_OFF,
                    target_room_id="living-room",
                ),
                AutomationAction(
                    action_type=ActionType.LIGHT_OFF,
                    target_room_id="bedroom-master",
                ),
            ],
            priority=2,
            tags=["night", "chronos", "lights"],
        ),
        AutomationRule(
            rule_id="auto-sleep-cameras",
            name="Night — Arm Cameras",
            description="Arm security cameras when going to sleep",
            trigger_type=TriggerType.SCHEDULE,
            trigger_config={"event": "sleep"},
            actions=[
                AutomationAction(
                    action_type=ActionType.CAMERA_ARM,
                    target_device_id="cam-01",
                ),
            ],
            priority=1,
            tags=["night", "security"],
        ),

        # --- Leave home ---
        AutomationRule(
            rule_id="auto-leave-security",
            name="Away — Arm Security & Close Blinds",
            description="When leaving home: arm cameras, close blinds, turn off plugs",
            trigger_type=TriggerType.SCHEDULE,
            trigger_config={"event": "leave"},
            actions=[
                AutomationAction(
                    action_type=ActionType.BLIND_CLOSE,
                    target_device_id="blind-ryse-01",
                ),
                AutomationAction(
                    action_type=ActionType.CAMERA_ARM,
                    target_device_id="cam-01",
                ),
                AutomationAction(
                    action_type=ActionType.DEVICE_OFF,
                    target_device_id="plug-tplink-01",
                ),
                AutomationAction(
                    action_type=ActionType.LIGHT_OFF,
                    target_room_id="living-room",
                ),
            ],
            priority=1,
            tags=["away", "security", "chronos"],
        ),

        # --- Arrive home ---
        AutomationRule(
            rule_id="auto-arrive-welcome",
            name="Home — Welcome Routine",
            description="When arriving home: open blinds, lights on, disarm entry camera",
            trigger_type=TriggerType.SCHEDULE,
            trigger_config={"event": "arrive"},
            actions=[
                AutomationAction(
                    action_type=ActionType.BLIND_OPEN,
                    target_device_id="blind-ryse-01",
                ),
                AutomationAction(
                    action_type=ActionType.LIGHT_ON,
                    target_room_id="living-room",
                    parameters={"brightness": 70},
                ),
                AutomationAction(
                    action_type=ActionType.CAMERA_DISARM,
                    target_device_id="cam-01",
                ),
            ],
            priority=1,
            tags=["arrive", "chronos"],
        ),

        # --- Sunset ---
        AutomationRule(
            rule_id="auto-sunset-blinds",
            name="Sunset — Close Blinds",
            description="Close blinds at sunset for privacy",
            trigger_type=TriggerType.SUNSET,
            actions=[
                AutomationAction(
                    action_type=ActionType.BLIND_CLOSE,
                    target_device_id="blind-ryse-01",
                ),
            ],
            priority=3,
            tags=["solar", "privacy", "blinds"],
        ),

        # --- Sunrise ---
        AutomationRule(
            rule_id="auto-sunrise-blinds",
            name="Sunrise — Open Blinds",
            description="Open blinds at sunrise for natural light",
            trigger_type=TriggerType.SUNRISE,
            actions=[
                AutomationAction(
                    action_type=ActionType.BLIND_OPEN,
                    target_device_id="blind-ryse-01",
                ),
            ],
            priority=3,
            tags=["solar", "blinds"],
        ),

        # --- Motion detection ---
        AutomationRule(
            rule_id="auto-motion-lights",
            name="Motion — Living Room Lights",
            description="Turn on living room lights on motion detection",
            trigger_type=TriggerType.OCCUPANCY,
            trigger_config={"state": "detected"},
            actions=[
                AutomationAction(
                    action_type=ActionType.LIGHT_ON,
                    target_room_id="living-room",
                    parameters={"brightness": 60},
                ),
            ],
            room_id="living-room",
            priority=4,
            tags=["occupancy", "lights"],
        ),
        AutomationRule(
            rule_id="auto-motion-cleared",
            name="No Motion — Dim Lights",
            description="Dim lights when no motion for 15 minutes",
            trigger_type=TriggerType.OCCUPANCY,
            trigger_config={"state": "cleared"},
            actions=[
                AutomationAction(
                    action_type=ActionType.LIGHT_DIM,
                    target_room_id="living-room",
                    parameters={"brightness": 20},
                    delay_seconds=900,
                ),
            ],
            room_id="living-room",
            priority=5,
            tags=["occupancy", "lights", "energy"],
        ),
    ]


def _default_scenes() -> list[Scene]:
    """Named presets for quick activation."""
    return [
        Scene(
            scene_id="scene-movie",
            name="Movie Mode",
            description="Dim lights, close blinds, TV on",
            actions=[
                AutomationAction(
                    action_type=ActionType.BLIND_CLOSE,
                    target_device_id="blind-ryse-01",
                ),
                AutomationAction(
                    action_type=ActionType.LIGHT_DIM,
                    target_room_id="living-room",
                    parameters={"brightness": 10, "color": "warm"},
                ),
                AutomationAction(
                    action_type=ActionType.DEVICE_ON,
                    target_device_id="tv-samsung-main",
                ),
            ],
            room_id="living-room",
            tags=["entertainment", "evening"],
        ),
        Scene(
            scene_id="scene-work",
            name="Focus Mode",
            description="Bright lights, blinds open for natural light, TV off",
            actions=[
                AutomationAction(
                    action_type=ActionType.BLIND_OPEN,
                    target_device_id="blind-ryse-01",
                ),
                AutomationAction(
                    action_type=ActionType.LIGHT_ON,
                    target_room_id="office",
                    parameters={"brightness": 100, "color": "daylight"},
                ),
                AutomationAction(
                    action_type=ActionType.DEVICE_OFF,
                    target_device_id="tv-samsung-main",
                ),
            ],
            tags=["productivity", "daytime"],
        ),
        Scene(
            scene_id="scene-away",
            name="Away Mode",
            description="Everything off, cameras armed, blinds closed",
            actions=[
                AutomationAction(
                    action_type=ActionType.BLIND_CLOSE,
                    target_device_id="blind-ryse-01",
                ),
                AutomationAction(action_type=ActionType.LIGHT_OFF, target_room_id="living-room"),
                AutomationAction(action_type=ActionType.LIGHT_OFF, target_room_id="bedroom-master"),
                AutomationAction(action_type=ActionType.LIGHT_OFF, target_room_id="office"),
                AutomationAction(action_type=ActionType.DEVICE_OFF, target_device_id="plug-tplink-01"),
                AutomationAction(action_type=ActionType.DEVICE_OFF, target_device_id="tv-samsung-main"),
                AutomationAction(action_type=ActionType.CAMERA_ARM, target_device_id="cam-01"),
            ],
            tags=["security", "away"],
        ),
        Scene(
            scene_id="scene-goodnight",
            name="Goodnight",
            description="Full shutdown — sleep mode for the house",
            actions=[
                AutomationAction(action_type=ActionType.BLIND_CLOSE, target_device_id="blind-ryse-01"),
                AutomationAction(action_type=ActionType.LIGHT_OFF, target_room_id="living-room"),
                AutomationAction(action_type=ActionType.LIGHT_OFF, target_room_id="office"),
                AutomationAction(
                    action_type=ActionType.LIGHT_DIM,
                    target_room_id="bedroom-master",
                    parameters={"brightness": 5, "color": "warm"},
                ),
                AutomationAction(action_type=ActionType.DEVICE_OFF, target_device_id="tv-samsung-main"),
                AutomationAction(action_type=ActionType.DEVICE_OFF, target_device_id="plug-tplink-01"),
                AutomationAction(action_type=ActionType.CAMERA_ARM, target_device_id="cam-01"),
            ],
            tags=["night", "security"],
        ),
    ]
