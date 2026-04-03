"""Tests for homelink/lan_security.py — VLAN policy, DNS blocking, credential audit."""

from unittest.mock import patch

import pytest

from guardian_one.homelink.devices import (
    DeviceCategory,
    DeviceRecord,
    DeviceRegistry,
    NetworkSegment,
)
from guardian_one.homelink.lan_security import (
    ALL_BLOCKLISTS,
    ECHO_BLOCKLIST,
    GOVEE_BLOCKLIST,
    HUE_BLOCKLIST,
    KASA_BLOCKLIST,
    LG_TV_BLOCKLIST,
    RING_BLOCKLIST,
    RYSE_BLOCKLIST,
    VLAN_POLICIES,
    LanSecurityAuditor,
)


# --- Fixtures ---

def _make_device(device_id, name, category, segment, **kwargs):
    return DeviceRecord(
        device_id=device_id,
        name=name,
        category=category,
        manufacturer="TestCo",
        network_segment=segment,
        **kwargs,
    )


@pytest.fixture
def registry():
    return DeviceRegistry()


# --- DNS Blocklist Tests ---

class TestDnsBlocklists:

    def test_all_known_blocklists_present(self):
        expected = [
            KASA_BLOCKLIST, HUE_BLOCKLIST, GOVEE_BLOCKLIST,
            LG_TV_BLOCKLIST, RING_BLOCKLIST, ECHO_BLOCKLIST, RYSE_BLOCKLIST,
        ]
        for bl in expected:
            assert bl in ALL_BLOCKLISTS
        assert len(ALL_BLOCKLISTS) >= len(expected)

    @pytest.mark.parametrize("blocklist,vendor", [
        (KASA_BLOCKLIST, "TP-Link Kasa"),
        (HUE_BLOCKLIST, "Philips Hue"),
        (GOVEE_BLOCKLIST, "Govee"),
        (LG_TV_BLOCKLIST, "LG WebOS TV"),
        (RING_BLOCKLIST, "Ring (Amazon)"),
        (ECHO_BLOCKLIST, "Amazon Echo"),
        (RYSE_BLOCKLIST, "Ryse SmartBridge"),
    ])
    def test_blocklist_vendor_names(self, blocklist, vendor):
        assert blocklist.vendor == vendor

    @pytest.mark.parametrize("blocklist", [
        KASA_BLOCKLIST, HUE_BLOCKLIST, GOVEE_BLOCKLIST, LG_TV_BLOCKLIST,
    ])
    def test_blockable_vendors_have_domains(self, blocklist):
        """Vendors with local-capable devices should have domains to block."""
        total = len(blocklist.domains) + len(blocklist.wildcard_domains)
        assert total > 0, f"{blocklist.vendor} should have blockable domains"

    def test_ring_and_echo_cannot_block(self):
        """Cloud-only devices have no blockable domains."""
        assert len(RING_BLOCKLIST.domains) == 0
        assert len(RING_BLOCKLIST.wildcard_domains) == 0
        assert len(ECHO_BLOCKLIST.domains) == 0
        assert len(ECHO_BLOCKLIST.wildcard_domains) == 0

    def test_kasa_cloud_domains(self):
        assert "n-devs.tplinkcloud.com" in KASA_BLOCKLIST.domains
        assert "*.tplinkcloud.com" in KASA_BLOCKLIST.wildcard_domains

    def test_lg_tv_has_acr_and_ad_domains(self):
        domains = LG_TV_BLOCKLIST.domains
        assert any("lgsmartad" in d for d in domains)
        assert any("lgappstv" in d for d in domains)

    def test_all_blocklists_have_notes(self):
        for bl in ALL_BLOCKLISTS:
            assert bl.notes, f"{bl.vendor} blocklist missing notes"


# --- VLAN Policy Tests ---

class TestVlanPolicies:

    def test_iot_devices_require_iot_vlan(self):
        iot_categories = {
            DeviceCategory.SMART_PLUG,
            DeviceCategory.SMART_LIGHT,
            DeviceCategory.SMART_BLIND,
            DeviceCategory.SMART_TV,
            DeviceCategory.SECURITY_CAMERA,
            DeviceCategory.MEDIA_PLAYER,
            DeviceCategory.SENSOR,
            DeviceCategory.MOTION_DETECTOR,
        }
        for policy in VLAN_POLICIES:
            if policy.category in iot_categories:
                assert policy.required_segment == NetworkSegment.IOT_VLAN, \
                    f"{policy.category} should require IOT_VLAN"

    def test_network_infra_on_trusted_lan(self):
        policy = next(p for p in VLAN_POLICIES if p.category == DeviceCategory.NETWORK_INFRA)
        assert policy.required_segment == NetworkSegment.TRUSTED_LAN

    def test_security_tool_not_networked(self):
        policy = next(p for p in VLAN_POLICIES if p.category == DeviceCategory.SECURITY_TOOL)
        assert policy.required_segment == NetworkSegment.NOT_NETWORKED

    def test_all_policies_have_reasons(self):
        for policy in VLAN_POLICIES:
            assert policy.reason, f"VLAN policy for {policy.category} missing reason"


# --- LanSecurityAuditor Tests ---

class TestVlanViolations:

    def test_no_violations_when_correct_segment(self, registry):
        """Device on correct VLAN = no violation."""
        device = _make_device("plug-01", "Kasa Plug", DeviceCategory.SMART_PLUG,
                              NetworkSegment.IOT_VLAN)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        violations = auditor.vlan_violations()
        assert len(violations) == 0

    def test_violation_when_iot_on_trusted_lan(self, registry):
        """Smart plug on TRUSTED_LAN should trigger violation."""
        device = _make_device("plug-01", "Kasa Plug", DeviceCategory.SMART_PLUG,
                              NetworkSegment.TRUSTED_LAN)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        violations = auditor.vlan_violations()
        assert len(violations) == 1
        assert violations[0]["device_id"] == "plug-01"
        assert violations[0]["current_segment"] == "trusted_lan"
        assert violations[0]["required_segment"] == "iot_vlan"

    def test_multiple_violations(self, registry):
        registry.register(_make_device("plug-01", "Plug", DeviceCategory.SMART_PLUG,
                                       NetworkSegment.TRUSTED_LAN))
        registry.register(_make_device("light-01", "Light", DeviceCategory.SMART_LIGHT,
                                       NetworkSegment.TRUSTED_LAN))
        registry.register(_make_device("tv-01", "TV", DeviceCategory.SMART_TV,
                                       NetworkSegment.GUEST))
        auditor = LanSecurityAuditor(registry)
        violations = auditor.vlan_violations()
        assert len(violations) == 3

    def test_no_policy_for_category_is_not_violation(self, registry):
        """Categories without a VLAN policy don't trigger violations."""
        device = _make_device("other-01", "Unknown", DeviceCategory.OTHER,
                              NetworkSegment.TRUSTED_LAN)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        violations = auditor.vlan_violations()
        assert len(violations) == 0


class TestCloudDependentDevices:

    def test_cloud_device_flagged(self, registry):
        device = _make_device("ring-01", "Ring Doorbell", DeviceCategory.SECURITY_CAMERA,
                              NetworkSegment.IOT_VLAN, local_api_only=False)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        cloud = auditor.cloud_dependent_devices()
        assert len(cloud) == 1
        assert cloud[0]["name"] == "Ring Doorbell"

    def test_local_device_not_flagged(self, registry):
        device = _make_device("plug-01", "Kasa Plug", DeviceCategory.SMART_PLUG,
                              NetworkSegment.IOT_VLAN, local_api_only=True)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        cloud = auditor.cloud_dependent_devices()
        assert len(cloud) == 0

    def test_network_infra_excluded(self, registry):
        """Network infra is never flagged as cloud-dependent."""
        device = _make_device("router-01", "Router", DeviceCategory.NETWORK_INFRA,
                              NetworkSegment.TRUSTED_LAN, local_api_only=False)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        cloud = auditor.cloud_dependent_devices()
        assert len(cloud) == 0

    def test_vehicle_excluded(self, registry):
        device = _make_device("car-01", "Car", DeviceCategory.VEHICLE,
                              NetworkSegment.NOT_NETWORKED, local_api_only=False)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        cloud = auditor.cloud_dependent_devices()
        assert len(cloud) == 0


class TestDefaultCredentials:

    def test_default_password_flagged(self, registry):
        device = _make_device("cam-01", "Camera", DeviceCategory.SECURITY_CAMERA,
                              NetworkSegment.IOT_VLAN, default_password_changed=False)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        creds = auditor.default_credential_devices()
        assert len(creds) == 1
        assert creds[0]["severity"] == "critical"

    def test_changed_password_not_flagged(self, registry):
        device = _make_device("cam-01", "Camera", DeviceCategory.SECURITY_CAMERA,
                              NetworkSegment.IOT_VLAN, default_password_changed=True)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        creds = auditor.default_credential_devices()
        assert len(creds) == 0


class TestDnsBlockReport:

    def test_report_structure(self, registry):
        auditor = LanSecurityAuditor(registry)
        report = auditor.dns_block_report()
        assert "total_domains" in report
        assert "total_wildcards" in report
        assert "vendors" in report
        assert "pihole_blocklist" in report
        assert "pihole_wildcards" in report
        assert report["total_domains"] > 0

    def test_pihole_lists_are_sorted_and_deduplicated(self, registry):
        auditor = LanSecurityAuditor(registry)
        report = auditor.dns_block_report()
        domains = report["pihole_blocklist"]
        assert domains == sorted(set(domains))
        wildcards = report["pihole_wildcards"]
        assert wildcards == sorted(set(wildcards))

    def test_vendor_blockable_flag(self, registry):
        auditor = LanSecurityAuditor(registry)
        report = auditor.dns_block_report()
        for vendor in report["vendors"]:
            if vendor["vendor"] in ("Ring (Amazon)", "Amazon Echo"):
                assert vendor["blockable"] is False
            elif vendor["vendor"] in ("TP-Link Kasa", "Philips Hue", "Govee"):
                assert vendor["blockable"] is True


class TestFullAudit:

    @patch("guardian_one.homelink.lan_security._dns_blocking_deployed", return_value=True)
    def test_clean_audit_low_risk(self, mock_dns, registry):
        """No devices = low risk score."""
        auditor = LanSecurityAuditor(registry)
        audit = auditor.full_audit()
        assert audit["risk_score"] == 1
        assert audit["vlan_violation_count"] == 0
        assert audit["cloud_dependent_count"] == 0
        assert audit["default_credential_count"] == 0

    @patch("guardian_one.homelink.lan_security._dns_blocking_deployed", return_value=True)
    def test_default_credentials_raise_risk(self, mock_dns, registry):
        device = _make_device("cam-01", "Camera", DeviceCategory.SECURITY_CAMERA,
                              NetworkSegment.IOT_VLAN, default_password_changed=False)
        registry.register(device)
        auditor = LanSecurityAuditor(registry)
        audit = auditor.full_audit()
        assert audit["risk_score"] >= 4

    @patch("guardian_one.homelink.lan_security._dns_blocking_deployed", return_value=False)
    def test_no_dns_blocking_raises_risk(self, mock_dns, registry):
        auditor = LanSecurityAuditor(registry)
        audit = auditor.full_audit()
        assert audit["risk_score"] >= 3

    @patch("guardian_one.homelink.lan_security._dns_blocking_deployed", return_value=True)
    def test_many_vlan_violations_raise_risk(self, mock_dns, registry):
        for i in range(4):
            registry.register(_make_device(
                f"plug-{i}", f"Plug {i}", DeviceCategory.SMART_PLUG,
                NetworkSegment.TRUSTED_LAN,
            ))
        auditor = LanSecurityAuditor(registry)
        audit = auditor.full_audit()
        assert audit["risk_score"] >= 3

    @patch("guardian_one.homelink.lan_security._dns_blocking_deployed", return_value=True)
    def test_audit_summary_text(self, mock_dns, registry):
        registry.register(_make_device(
            "plug-01", "Plug", DeviceCategory.SMART_PLUG,
            NetworkSegment.TRUSTED_LAN, default_password_changed=False,
        ))
        auditor = LanSecurityAuditor(registry)
        audit = auditor.full_audit()
        assert "1 VLAN violations" in audit["summary"]
        assert "1 default credentials" in audit["summary"]

    @patch("guardian_one.homelink.lan_security._dns_blocking_deployed", return_value=True)
    def test_action_items_generated(self, mock_dns, registry):
        registry.register(_make_device(
            "plug-01", "Plug", DeviceCategory.SMART_PLUG,
            NetworkSegment.TRUSTED_LAN, default_password_changed=False,
        ))
        auditor = LanSecurityAuditor(registry)
        audit = auditor.full_audit()
        priorities = [item["priority"] for item in audit["action_items"]]
        assert "CRITICAL" in priorities  # default password
        assert "HIGH" in priorities  # VLAN violation


class TestAuditText:

    @patch("guardian_one.homelink.lan_security._dns_blocking_deployed", return_value=True)
    def test_audit_text_contains_sections(self, mock_dns, registry):
        auditor = LanSecurityAuditor(registry)
        text = auditor.audit_text()
        assert "LAN SECURITY AUDIT" in text
        assert "VLAN ISOLATION" in text
        assert "CLOUD DEPENDENCIES" in text
        assert "DNS BLOCKING" in text
        assert "DEFAULT CREDENTIALS" in text
        assert "ACTION ITEMS" in text

    @patch("guardian_one.homelink.lan_security._dns_blocking_deployed", return_value=True)
    def test_audit_text_clean_shows_checkmarks(self, mock_dns, registry):
        auditor = LanSecurityAuditor(registry)
        text = auditor.audit_text()
        assert "All devices on correct segments" in text
        assert "All passwords changed" in text
