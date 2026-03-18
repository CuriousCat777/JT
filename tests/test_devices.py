"""Tests for H.O.M.E. L.I.N.K. device management.

Covers:
- DeviceRecord model
- DeviceRegistry inventory and queries
- DeviceAgent lifecycle, security audit, VLAN checks
- Integration with registry threat models
"""

from __future__ import annotations

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.homelink.devices import (
    DeviceCategory,
    DeviceProtocol,
    DeviceRecord,
    DeviceRegistry,
    DeviceStatus,
    FirmwareInfo,
    NetworkSegment,
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
        assert reg.get("test-device-01") is None

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
        assert len(reg.by_segment(NetworkSegment.TRUSTED_LAN)) == 1

    def test_by_protocol(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="wifi", protocols=[DeviceProtocol.WIFI]))
        reg.register(_sample_device(device_id="zigbee", protocols=[DeviceProtocol.ZIGBEE]))
        assert len(reg.by_protocol(DeviceProtocol.WIFI)) == 1
        assert len(reg.by_protocol(DeviceProtocol.ZIGBEE)) == 1

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
        reg.register(_sample_device(device_id="b", location="front_door"))
        assert len(reg.by_location("living_room")) == 1
        assert len(reg.by_location("LIVING_ROOM")) == 1  # case insensitive

    def test_update_status(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device())
        assert reg.update_status("test-device-01", DeviceStatus.ONLINE) is True
        assert reg.get("test-device-01").status == DeviceStatus.ONLINE
        assert reg.get("test-device-01").last_seen != ""
        assert reg.update_status("nonexistent", DeviceStatus.ONLINE) is False

    def test_device_count_by_category(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(device_id="p1", category=DeviceCategory.SMART_PLUG))
        reg.register(_sample_device(device_id="p2", category=DeviceCategory.SMART_PLUG))
        reg.register(_sample_device(device_id="c1", category=DeviceCategory.SECURITY_CAMERA))
        counts = reg.device_count_by_category()
        assert counts["smart_plug"] == 2
        assert counts["security_camera"] == 1

    def test_load_defaults(self) -> None:
        reg = DeviceRegistry()
        reg.load_defaults()
        devices = reg.all_devices()
        assert len(devices) >= 7  # cam, motion, tv, plug, hue, govee, vehicle, flipper
        ids = [d.device_id for d in devices]
        assert "flipper-zero" in ids
        assert "light-hue-bridge" in ids
        assert "plug-tplink-01" in ids
        assert "vehicle-01" in ids
        assert "cam-01" in ids


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
        assert "Default password" in critical_issues[0]["issue"]

    def test_trusted_lan_iot_flagged(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(
            category=DeviceCategory.SMART_PLUG,
            network_segment=NetworkSegment.TRUSTED_LAN,
        ))
        audit = reg.security_audit()
        isolation_issues = [i for i in audit["issues"] if "isolate" in i["issue"].lower()]
        assert len(isolation_issues) >= 1

    def test_camera_cloud_dependency_flagged(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(
            category=DeviceCategory.SECURITY_CAMERA,
            local_api_only=False,
        ))
        audit = reg.security_audit()
        cloud_issues = [i for i in audit["issues"] if "cloud" in i["issue"].lower()]
        assert len(cloud_issues) >= 1

    def test_camera_encryption_flagged(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(
            category=DeviceCategory.SECURITY_CAMERA,
            encryption_enabled=False,
        ))
        audit = reg.security_audit()
        enc_issues = [i for i in audit["issues"] if "encrypt" in i["issue"].lower()]
        assert len(enc_issues) >= 1

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
        """Default devices should have security issues (passwords not changed yet)."""
        reg = DeviceRegistry()
        reg.load_defaults()
        audit = reg.security_audit()
        assert audit["issue_count"] > 0
        assert audit["risk_score"] >= 1


# ========================================================================
# DeviceAgent tests
# ========================================================================

class TestDeviceAgent:
    def test_initialize(self) -> None:
        agent = _make_agent()
        agent.initialize()
        assert len(agent.device_registry.all_devices()) >= 7

    def test_run_returns_report(self) -> None:
        agent = _make_agent()
        agent.initialize()
        report = agent.run()
        assert report.agent_name == "device_agent"
        assert "devices managed" in report.summary
        assert "security issues" in report.summary
        assert report.data["device_count"] >= 7

    def test_report_without_run(self) -> None:
        agent = _make_agent()
        agent.initialize()
        report = agent.report()
        assert report.agent_name == "device_agent"
        assert report.data["device_count"] >= 7

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
        assert agent.remove_device("to-remove") is False

    def test_get_device(self) -> None:
        agent = _make_agent()
        agent.initialize()
        assert agent.get_device("flipper-zero") is not None
        assert agent.get_device("nonexistent") is None

    def test_scan_network_stub(self) -> None:
        agent = _make_agent()
        agent.initialize()
        results = agent.scan_network()
        assert results == []  # stub returns empty

    def test_detect_unknown_devices_empty(self) -> None:
        agent = _make_agent()
        agent.initialize()
        unknown = agent.detect_unknown_devices()
        assert unknown == []

    def test_ecosystem_queries(self) -> None:
        agent = _make_agent()
        agent.initialize()
        assert len(agent.hue_devices()) >= 1
        assert len(agent.govee_devices()) >= 1
        assert len(agent.tplink_devices()) >= 1
        assert len(agent.cameras()) >= 1
        assert len(agent.security_devices()) >= 3  # cam + motion + flipper

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
        assert "bad-plug" in misplaced[0][0]

    def test_firmware_check(self) -> None:
        reg = DeviceRegistry()
        reg.register(_sample_device(
            device_id="old-fw",
            firmware=FirmwareInfo(current_version="1.0", latest_available="2.0"),
        ))
        reg.register(_sample_device(
            device_id="current-fw",
            firmware=FirmwareInfo(current_version="2.0", latest_available="2.0"),
        ))
        agent = _make_agent(reg)
        needs_update = agent._check_firmware_status()
        assert "old-fw" in needs_update
        assert "current-fw" not in needs_update

    def test_status_text(self) -> None:
        agent = _make_agent()
        agent.initialize()
        text = agent.status_text()
        assert "DEVICE MANAGEMENT" in text
        assert "Security risk:" in text
        assert "[CAM]" in text or "[LGT]" in text

    def test_run_alerts_on_critical_issues(self) -> None:
        agent = _make_agent()
        agent.initialize()
        report = agent.run()
        # Default devices have passwords not changed — should trigger alerts
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

    def test_iot_threat_models_complete(self) -> None:
        from guardian_one.homelink.registry import (
            TPLINK_KASA_INTEGRATION,
            PHILIPS_HUE_INTEGRATION,
            GOVEE_INTEGRATION,
            SECURITY_CAMERA_INTEGRATION,
            VEHICLE_INTEGRATION,
            FLIPPER_ZERO_INTEGRATION,
            SMART_TV_INTEGRATION,
        )
        for integration in [
            TPLINK_KASA_INTEGRATION,
            PHILIPS_HUE_INTEGRATION,
            GOVEE_INTEGRATION,
            SECURITY_CAMERA_INTEGRATION,
            VEHICLE_INTEGRATION,
            FLIPPER_ZERO_INTEGRATION,
            SMART_TV_INTEGRATION,
        ]:
            assert len(integration.threat_model) == 5, f"{integration.name} missing threats"
            assert integration.failure_impact != ""
            assert integration.rollback_procedure != ""
            assert integration.owner_agent == "device_agent"

    def test_camera_has_critical_threats(self) -> None:
        from guardian_one.homelink.registry import SECURITY_CAMERA_INTEGRATION
        critical = [t for t in SECURITY_CAMERA_INTEGRATION.threat_model if t.severity == "critical"]
        assert len(critical) >= 2  # default creds + firmware RCE

    def test_vehicle_has_critical_threats(self) -> None:
        from guardian_one.homelink.registry import VEHICLE_INTEGRATION
        critical = [t for t in VEHICLE_INTEGRATION.threat_model if t.severity == "critical"]
        assert len(critical) >= 1  # API compromise

    def test_device_agent_integrations_by_agent(self) -> None:
        from guardian_one.homelink.registry import IntegrationRegistry
        reg = IntegrationRegistry()
        reg.load_defaults()
        device_integrations = reg.by_agent("device_agent")
        assert len(device_integrations) == 7
