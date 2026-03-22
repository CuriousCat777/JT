"""Tests for H.O.M.E. L.I.N.K. device management.

Covers:
- DeviceRecord model
- DeviceRegistry inventory and queries
- Room model and device-room mapping
- Flipper Zero profiles
- Automation engine (rules, scenes, triggers)
- DeviceAgent lifecycle, security audit, VLAN checks, event handling
- Integration with registry threat models
"""

from __future__ import annotations

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.homelink.automations import (
    ActionType,
    AutomationAction,
    AutomationEngine,
    AutomationRule,
    AutomationStatus,
    Scene,
    TriggerType,
)
from guardian_one.homelink.devices import (
    DeviceCategory,
    DeviceProtocol,
    DeviceRecord,
    DeviceRegistry,
    DeviceStatus,
    FlipperCapability,
    FlipperProfile,
    FirmwareInfo,
    NetworkSegment,
    Room,
    RoomType,
)
from guardian_one.agents.device_agent import DeviceAgent


# ========================================================================
# Fixtures
# ========================================================================

def _make_audit() -> AuditLog:
    return AuditLog()


def _make_agent(registry: DeviceRegistry | None = None) -> DeviceAgent:
    config = AgentConfig(
        name="device_agent", enabled=True,
        allowed_resources=["devices", "network"],
    )
    return DeviceAgent(config=config, audit=_make_audit(), device_registry=registry)


def _sample_device(**overrides) -> DeviceRecord:
    defaults = dict(
        device_id="test-device-01",
        name="Test Device",
        category=DeviceCategory.SMART_PLUG,
        manufacturer="TestMfg",
        protocols=[DeviceProtocol.WIFI],
        network_segment=NetworkSegment.IOT_VLAN,
    )
    defaults.update(overrides)
    return DeviceRecord(**defaults)


# ========================================================================
# DeviceRecord tests
# ========================================================================

class TestDeviceRecord:
    def test_create_device(self) -> None:
        d = _sample_device()
        assert d.device_id == "test-device-01"
        assert d.category == DeviceCategory.SMART_PLUG
        assert d.status == DeviceStatus.UNKNOWN
        assert d.default_password_changed is False

    def test_device_defaults(self) -> None:
        d = _sample_device()
        assert d.ip_address == ""
        assert d.mac_address == ""
        assert d.local_api_only is False
        assert d.encryption_enabled is False
        assert d.firmware.current_version == "unknown"

    def test_firmware_info(self) -> None:
        fw = FirmwareInfo(current_version="1.2.3", latest_available="1.3.0")
        d = _sample_device(firmware=fw)
        assert d.firmware.current_version == "1.2.3"
        assert d.firmware.latest_available == "1.3.0"
        assert d.firmware.auto_update is False

    def test_smart_blind_category(self) -> None:
        d = _sample_device(category=DeviceCategory.SMART_BLIND)
        assert d.category == DeviceCategory.SMART_BLIND


# ========================================================================
# DeviceRegistry tests
# ========================================================================

class TestDeviceRegistry:
    def test_register_and_get(self) -> None:
        reg = DeviceRegistry()
        d = _sample_device()
        reg.register(d)
        assert reg.get("test-device-01") is d
        assert reg.get("nonexistent") is None

    def test_remove_device(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device())
        assert reg.remove("test-device-01") is True
        assert reg.remove("test-device-01") is False

    def test_all_devices(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="a"))
        reg.register(_sample_device(device_id="b"))
        assert len(reg.all_devices()) == 2

    def test_by_category(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="plug", category=DeviceCategory.SMART_PLUG))
        reg.register(_sample_device(device_id="cam", category=DeviceCategory.SECURITY_CAMERA))
        assert len(reg.by_category(DeviceCategory.SMART_PLUG)) == 1
        assert len(reg.by_category(DeviceCategory.SECURITY_CAMERA)) == 1

    def test_by_segment(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="iot", network_segment=NetworkSegment.IOT_VLAN))
        reg.register(_sample_device(device_id="lan", network_segment=NetworkSegment.TRUSTED_LAN))
        assert len(reg.by_segment(NetworkSegment.IOT_VLAN)) == 1

    def test_by_protocol(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="wifi", protocols=[DeviceProtocol.WIFI]))
        reg.register(_sample_device(device_id="zigbee", protocols=[DeviceProtocol.ZIGBEE]))
        assert len(reg.by_protocol(DeviceProtocol.WIFI)) == 1

    def test_by_status(self) -> None:
        reg = DeviceRegistry()
        d = _sample_device()
        d.status = DeviceStatus.ONLINE
        reg.register(d)
        assert len(reg.by_status(DeviceStatus.ONLINE)) == 1
        assert len(reg.by_status(DeviceStatus.OFFLINE)) == 0

    def test_by_location(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="a", location="living_room"))
        assert len(reg.by_location("LIVING_ROOM")) == 1  # case insensitive

    def test_update_status(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device())
        assert reg.update_status("test-device-01", DeviceStatus.ONLINE) is True
        assert reg.get("test-device-01").status == DeviceStatus.ONLINE
        assert reg.update_status("nonexistent", DeviceStatus.ONLINE) is False

    def test_device_count_by_category(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="p1", category=DeviceCategory.SMART_PLUG))
        reg.register(_sample_device(device_id="p2", category=DeviceCategory.SMART_PLUG))
        counts = reg.device_count_by_category()
        assert counts["smart_plug"] == 2

    def test_load_defaults(self) -> None:
        reg = DeviceRegistry()
        reg.load_defaults()
        devices = reg.all_devices()
        assert len(devices) >= 9  # cam, motion, tv, plug, hue, govee, ryse, vehicle, flipper
        ids = [d.device_id for d in devices]
        assert "flipper-zero" in ids
        assert "blind-ryse-01" in ids
        assert "light-hue-bridge" in ids

    def test_load_defaults_has_rooms(self) -> None:
        reg = DeviceRegistry()
        reg.load_defaults()
        rooms = reg.all_rooms()
        assert len(rooms) >= 5
        room_ids = [r.room_id for r in rooms]
        assert "living-room" in room_ids
        assert "bedroom-master" in room_ids
        assert "office" in room_ids

    def test_load_defaults_has_flipper_profiles(self) -> None:
        reg = DeviceRegistry()
        reg.load_defaults()
        profiles = reg.all_flipper_profiles()
        assert len(profiles) >= 6
        profile_ids = [p.device_id for p in profiles]
        assert "tv-main" in profile_ids
        assert "blind-ryse-01" in profile_ids


# ========================================================================
# Room model tests
# ========================================================================

class TestRoomModel:
    def test_add_and_get_room(self) -> None:
        reg = DeviceRegistry()
        room = Room(room_id="test-room", name="Test Room", room_type=RoomType.BEDROOM)
        reg.add_room(room)
        assert reg.get_room("test-room") is room

    def test_devices_in_room(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="d1"))
        reg.register(_sample_device(device_id="d2"))
        room = Room(room_id="r1", name="Room 1", room_type=RoomType.LIVING_ROOM,
                     device_ids=["d1", "d2"])
        reg.add_room(room)
        assert len(reg.devices_in_room("r1")) == 2

    def test_room_for_device(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="d1"))
        room = Room(room_id="r1", name="Room 1", room_type=RoomType.OFFICE,
                     device_ids=["d1"])
        reg.add_room(room)
        assert reg.room_for_device("d1").room_id == "r1"
        assert reg.room_for_device("nonexistent") is None

    def test_rooms_by_type(self) -> None:
        reg = DeviceRegistry()
        reg.add_room(Room(room_id="bed1", name="Bed", room_type=RoomType.BEDROOM))
        reg.add_room(Room(room_id="off1", name="Office", room_type=RoomType.OFFICE))
        assert len(reg.rooms_by_type(RoomType.BEDROOM)) == 1

    def test_room_summary(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="d1"))
        room = Room(room_id="r1", name="Test", room_type=RoomType.LIVING_ROOM,
                     device_ids=["d1"], auto_lights=True, auto_blinds=True)
        reg.add_room(room)
        summary = reg.room_summary()
        assert len(summary) == 1
        assert summary[0]["device_count"] == 1
        assert summary[0]["auto_lights"] is True


# ========================================================================
# Flipper Zero profile tests
# ========================================================================

class TestFlipperProfiles:
    def test_add_and_get_profile(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="tv"))
        profile = FlipperProfile(
            device_id="tv",
            capabilities=[FlipperCapability.IR_CAPTURE, FlipperCapability.IR_TRANSMIT],
            ir_remote_file="infrared/tv.ir",
        )
        reg.add_flipper_profile(profile)
        assert reg.get_flipper_profile("tv") is profile

    def test_flipper_controllable_devices(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="tv"))
        reg.register(_sample_device(device_id="no-flipper"))
        reg.add_flipper_profile(FlipperProfile(
            device_id="tv", capabilities=[FlipperCapability.IR_TRANSMIT]))
        controllable = reg.flipper_controllable_devices()
        assert len(controllable) == 1
        assert controllable[0].device_id == "tv"


# ========================================================================
# Security audit tests
# ========================================================================

class TestSecurityAudit:
    def test_empty_registry_audit(self) -> None:
        reg = DeviceRegistry()
        audit = reg.security_audit()
        assert audit["total_devices"] == 0
        assert audit["risk_score"] == 0

    def test_default_password_flagged(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(default_password_changed=False))
        audit = reg.security_audit()
        critical_issues = [i for i in audit["issues"] if i["severity"] == "critical"]
        assert len(critical_issues) >= 1

    def test_trusted_lan_iot_flagged(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(
            category=DeviceCategory.SMART_PLUG,
            network_segment=NetworkSegment.TRUSTED_LAN,
        ))
        audit = reg.security_audit()
        isolation_issues = [i for i in audit["issues"] if "isolate" in i["issue"].lower()]
        assert len(isolation_issues) >= 1

    def test_secure_device_lower_risk(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(
            default_password_changed=True,
            upnp_disabled=True,
            firmware=FirmwareInfo(current_version="2.0.0"),
        ))
        audit = reg.security_audit()
        assert audit["risk_score"] <= 2

    def test_load_defaults_has_issues(self) -> None:
        reg = DeviceRegistry()
        reg.load_defaults()
        audit = reg.security_audit()
        assert audit["issue_count"] > 0


# ========================================================================
# Automation engine tests
# ========================================================================

class TestAutomationEngine:
    def test_add_and_get_rule(self) -> None:
        engine = AutomationEngine()
        rule = AutomationRule(
            rule_id="test-01", name="Test", description="Test rule",
            trigger_type=TriggerType.SCHEDULE,
        )
        engine.add_rule(rule)
        assert engine.get_rule("test-01") is rule

    def test_remove_rule(self) -> None:
        engine = AutomationEngine()
        engine.add_rule(AutomationRule(
            rule_id="r1", name="R", description="D", trigger_type=TriggerType.MANUAL))
        assert engine.remove_rule("r1") is True
        assert engine.remove_rule("r1") is False

    def test_enable_disable_rule(self) -> None:
        engine = AutomationEngine()
        engine.add_rule(AutomationRule(
            rule_id="r1", name="R", description="D", trigger_type=TriggerType.MANUAL))
        assert engine.disable_rule("r1") is True
        assert engine.get_rule("r1").status == AutomationStatus.DISABLED
        assert engine.enable_rule("r1") is True
        assert engine.get_rule("r1").status == AutomationStatus.ENABLED

    def test_rules_by_trigger(self) -> None:
        engine = AutomationEngine()
        engine.add_rule(AutomationRule(
            rule_id="s1", name="S", description="D", trigger_type=TriggerType.SCHEDULE))
        engine.add_rule(AutomationRule(
            rule_id="o1", name="O", description="D", trigger_type=TriggerType.OCCUPANCY))
        assert len(engine.rules_by_trigger(TriggerType.SCHEDULE)) == 1

    def test_evaluate_trigger_schedule(self) -> None:
        engine = AutomationEngine()
        engine.add_rule(AutomationRule(
            rule_id="wake", name="Wake", description="D",
            trigger_type=TriggerType.SCHEDULE,
            trigger_config={"event": "wake"},
            actions=[AutomationAction(
                action_type=ActionType.BLIND_OPEN, target_device_id="blind-01")],
        ))
        actions = engine.evaluate_trigger(TriggerType.SCHEDULE, {"event": "wake"})
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.BLIND_OPEN

    def test_evaluate_trigger_no_match(self) -> None:
        engine = AutomationEngine()
        engine.add_rule(AutomationRule(
            rule_id="wake", name="Wake", description="D",
            trigger_type=TriggerType.SCHEDULE,
            trigger_config={"event": "wake"},
            actions=[AutomationAction(action_type=ActionType.BLIND_OPEN)],
        ))
        actions = engine.evaluate_trigger(TriggerType.SCHEDULE, {"event": "sleep"})
        assert len(actions) == 0

    def test_evaluate_occupancy(self) -> None:
        engine = AutomationEngine()
        engine.add_rule(AutomationRule(
            rule_id="motion", name="Motion", description="D",
            trigger_type=TriggerType.OCCUPANCY,
            trigger_config={"state": "detected"},
            actions=[AutomationAction(
                action_type=ActionType.LIGHT_ON, target_room_id="living-room")],
        ))
        actions = engine.evaluate_trigger(TriggerType.OCCUPANCY, {"state": "detected"})
        assert len(actions) == 1
        assert actions[0].action_type == ActionType.LIGHT_ON

    def test_execution_count(self) -> None:
        engine = AutomationEngine()
        engine.add_rule(AutomationRule(
            rule_id="r1", name="R", description="D",
            trigger_type=TriggerType.MANUAL,
            actions=[AutomationAction(action_type=ActionType.DEVICE_ON)],
        ))
        engine.evaluate_trigger(TriggerType.MANUAL)
        engine.evaluate_trigger(TriggerType.MANUAL)
        assert engine.get_rule("r1").execution_count == 2

    def test_scene_activate(self) -> None:
        engine = AutomationEngine()
        engine.add_scene(Scene(
            scene_id="scene-test", name="Test", description="D",
            actions=[
                AutomationAction(action_type=ActionType.LIGHT_ON),
                AutomationAction(action_type=ActionType.BLIND_CLOSE),
            ],
        ))
        actions = engine.activate_scene("scene-test")
        assert len(actions) == 2

    def test_scene_not_found(self) -> None:
        engine = AutomationEngine()
        assert engine.activate_scene("nonexistent") == []

    def test_load_defaults(self) -> None:
        engine = AutomationEngine()
        engine.load_defaults()
        assert len(engine.all_rules()) >= 10
        assert len(engine.all_scenes()) >= 4
        # Should have rules for wake, sleep, leave, arrive, sunrise, sunset
        wake_rules = [r for r in engine.all_rules()
                      if r.trigger_config.get("event") == "wake"]
        assert len(wake_rules) >= 2  # blinds + lights

    def test_summary(self) -> None:
        engine = AutomationEngine()
        engine.load_defaults()
        summary = engine.summary()
        assert summary["total_rules"] >= 10
        assert summary["total_scenes"] >= 4
        assert summary["enabled_rules"] >= 10

    def test_execution_history(self) -> None:
        engine = AutomationEngine()
        engine.load_defaults()
        engine.evaluate_trigger(TriggerType.SCHEDULE, {"event": "wake"})
        history = engine.execution_history()
        assert len(history) >= 2  # At least blinds + lights rules


# ========================================================================
# DeviceAgent tests
# ========================================================================

class TestDeviceAgent:
    def test_initialize(self) -> None:
        agent = _make_agent()
        agent.initialize()
        assert len(agent.device_registry.all_devices()) >= 9
        assert len(agent.device_registry.all_rooms()) >= 5
        assert len(agent.automation.all_rules()) >= 10

    def test_run_returns_report(self) -> None:
        agent = _make_agent()
        agent.initialize()
        report = agent.run()
        assert report.agent_name == "device_agent"
        assert "devices managed" in report.summary
        assert report.data["device_count"] >= 9
        assert report.data["room_count"] >= 5
        assert report.data["automation_rules"] >= 10

    def test_report_without_run(self) -> None:
        agent = _make_agent()
        agent.initialize()
        report = agent.report()
        assert report.data["device_count"] >= 9

    def test_add_device(self) -> None:
        agent = _make_agent(DeviceRegistry())
        agent.initialize()
        count_before = len(agent.list_devices())
        agent.add_device(_sample_device(device_id="new-dev"))
        assert len(agent.list_devices()) == count_before + 1

    def test_remove_device(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="to-remove"))
        agent = _make_agent(reg)
        assert agent.remove_device("to-remove") is True

    def test_get_device(self) -> None:
        agent = _make_agent()
        agent.initialize()
        assert agent.get_device("flipper-zero") is not None
        assert agent.get_device("blind-ryse-01") is not None

    def test_handle_schedule_event_wake(self) -> None:
        agent = _make_agent()
        agent.initialize()
        results = agent.handle_schedule_event("wake")
        assert len(results) >= 2  # blinds + lights
        action_types = [r["action"] for r in results]
        assert "blind_open" in action_types

    def test_handle_schedule_event_sleep(self) -> None:
        agent = _make_agent()
        agent.initialize()
        results = agent.handle_schedule_event("sleep")
        assert len(results) >= 3  # blinds + lights + cameras
        action_types = [r["action"] for r in results]
        assert "blind_close" in action_types
        assert "camera_arm" in action_types

    def test_handle_schedule_event_leave(self) -> None:
        agent = _make_agent()
        agent.initialize()
        results = agent.handle_schedule_event("leave")
        assert len(results) >= 4

    def test_handle_schedule_event_arrive(self) -> None:
        agent = _make_agent()
        agent.initialize()
        results = agent.handle_schedule_event("arrive")
        assert len(results) >= 3

    def test_handle_solar_event(self) -> None:
        agent = _make_agent()
        agent.initialize()
        results = agent.handle_solar_event("sunset")
        assert len(results) >= 1
        assert results[0]["action"] == "blind_close"

    def test_handle_occupancy_event(self) -> None:
        agent = _make_agent()
        agent.initialize()
        results = agent.handle_occupancy_event("detected")
        assert len(results) >= 1

    def test_activate_scene_movie(self) -> None:
        agent = _make_agent()
        agent.initialize()
        results = agent.activate_scene("scene-movie")
        assert len(results) >= 3

    def test_activate_scene_goodnight(self) -> None:
        agent = _make_agent()
        agent.initialize()
        results = agent.activate_scene("scene-goodnight")
        assert len(results) >= 7

    def test_action_history(self) -> None:
        agent = _make_agent()
        agent.initialize()
        agent.handle_schedule_event("wake")
        history = agent.action_history()
        assert len(history) >= 2

    def test_ecosystem_queries(self) -> None:
        agent = _make_agent()
        agent.initialize()
        assert len(agent.hue_devices()) >= 1
        assert len(agent.govee_devices()) >= 1
        assert len(agent.tplink_devices()) >= 1
        assert len(agent.ryse_devices()) >= 1
        assert len(agent.blinds()) >= 1
        assert len(agent.cameras()) >= 1
        assert len(agent.security_devices()) >= 3

    def test_flipper_audit(self) -> None:
        agent = _make_agent()
        agent.initialize()
        flipper = agent.flipper_audit()
        assert flipper["total_profiles"] >= 6
        assert flipper["controllable_devices"] >= 6
        assert "ir_capture" in flipper["capabilities"]

    def test_vlan_isolation_check(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(
            device_id="bad-plug",
            category=DeviceCategory.SMART_PLUG,
            network_segment=NetworkSegment.TRUSTED_LAN,
        ))
        agent = _make_agent(reg)
        misplaced = agent._check_vlan_isolation()
        assert len(misplaced) == 1

    def test_dashboard_text(self) -> None:
        agent = _make_agent()
        agent.initialize()
        text = agent.dashboard_text()
        assert "CONTROL DASHBOARD" in text
        assert "ROOMS" in text
        assert "AUTOMATION RULES" in text
        assert "SCENES" in text
        assert "FLIPPER ZERO" in text
        assert "Ryse" in text or "blind" in text.lower()

    def test_run_alerts_on_critical_issues(self) -> None:
        agent = _make_agent()
        agent.initialize()
        report = agent.run()
        assert len(report.alerts) > 0 or report.data["security_audit"]["issue_count"] > 0


# ========================================================================
# Registry integration threat model tests
# ========================================================================

class TestDeviceRegistryIntegrations:
    def test_iot_integrations_registered(self) -> None:
        from guardian_one.homelink.registry import IntegrationRegistry
        reg = IntegrationRegistry()
        reg.load_defaults()
        names = reg.list_all()
        assert "tplink_kasa" in names
        assert "philips_hue" in names
        assert "govee" in names
        assert "security_cameras" in names
        assert "vehicle_telematics" in names
        assert "flipper_zero" in names
        assert "smart_tv" in names
        assert "ryse_smartshade" in names

    def test_iot_threat_models_complete(self) -> None:
        from guardian_one.homelink.registry import (
            TPLINK_KASA_INTEGRATION,
            PHILIPS_HUE_INTEGRATION,
            GOVEE_INTEGRATION,
            SECURITY_CAMERA_INTEGRATION,
            VEHICLE_INTEGRATION,
            FLIPPER_ZERO_INTEGRATION,
            SMART_TV_INTEGRATION,
            RYSE_SMARTSHADE_INTEGRATION,
        )
        for integration in [
            TPLINK_KASA_INTEGRATION, PHILIPS_HUE_INTEGRATION,
            GOVEE_INTEGRATION, SECURITY_CAMERA_INTEGRATION,
            VEHICLE_INTEGRATION, FLIPPER_ZERO_INTEGRATION,
            SMART_TV_INTEGRATION, RYSE_SMARTSHADE_INTEGRATION,
        ]:
            assert len(integration.threat_model) == 5, f"{integration.name} missing threats"
            assert integration.owner_agent == "device_agent"

    def test_camera_has_critical_threats(self) -> None:
        from guardian_one.homelink.registry import SECURITY_CAMERA_INTEGRATION
        critical = [t for t in SECURITY_CAMERA_INTEGRATION.threat_model if t.severity == "critical"]
        assert len(critical) >= 2

    def test_device_agent_integrations_by_agent(self) -> None:
        from guardian_one.homelink.registry import IntegrationRegistry
        reg = IntegrationRegistry()
        reg.load_defaults()
        device_integrations = reg.by_agent("device_agent")
        assert len(device_integrations) == 10  # 7 original + ryse + network_infra + ring
