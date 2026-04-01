"""Tests for the Sovereign IoT Local Control system.

Covers:
- NetworkScanner: parsing, classification, risk scoring
- MqttBrokerClient: in-memory mode, topic matching, pub/sub
- NetworkMonitor: anomaly detection, baseline, health tracking
- IoTSentinel agent: lifecycle, recommendations, approvals, dashboard
- TailscaleClient: status parsing
- NodeRedClient: flow management
- HomeAssistantClient: entity management, service calls, dashboard modules
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.homelink.network_scanner import (
    DeviceClassification,
    DiscoveredDevice,
    NetworkScanner,
)
from guardian_one.homelink.mqtt_broker import (
    MqttBrokerClient,
    MqttBrokerConfig,
    MqttMessage,
)
from guardian_one.homelink.network_monitor import (
    AlertSeverity,
    AnomalyType,
    NetworkAnomaly,
    NetworkMonitor,
)
from guardian_one.agents.iot_sentinel import IoTSentinel, RecommendationAction
from guardian_one.homelink.tailscale import TailscaleClient, TailscaleConfig, TailscalePeer
from guardian_one.homelink.nodered import NodeRedClient, NodeRedConfig, NodeRedFlow
from guardian_one.homelink.homeassistant import (
    HomeAssistantClient,
    HomeAssistantConfig,
    HAEntity,
    HAEntityDomain,
    HAServiceCall,
)


# ========================================================================
# Fixtures
# ========================================================================

def _make_audit() -> AuditLog:
    return AuditLog()


def _make_scanner(known_macs: set[str] | None = None) -> NetworkScanner:
    return NetworkScanner(
        subnet="192.168.1.0/24",
        audit=_make_audit(),
        known_macs=known_macs or set(),
    )


def _make_sentinel(**kwargs) -> IoTSentinel:
    config = AgentConfig(
        name="iot_sentinel",
        enabled=True,
        allowed_resources=["network", "devices", "mqtt", "security"],
        custom={
            "subnet": "192.168.1.0/24",
            "scan_interval_seconds": 60,
            "known_macs": [],
        },
    )
    return IoTSentinel(
        config=config,
        audit=_make_audit(),
        **kwargs,
    )


# ========================================================================
# NetworkScanner tests
# ========================================================================

class TestNetworkScanner:
    """Tests for LAN device discovery."""

    def test_init_defaults(self):
        scanner = _make_scanner()
        assert scanner.subnet == "192.168.1.0/24"
        assert scanner.scan_count == 0

    def test_update_known_macs(self):
        scanner = _make_scanner()
        scanner.update_known_macs({"AA:BB:CC:DD:EE:FF"})
        assert "aa:bb:cc:dd:ee:ff" in scanner._known_macs

    def test_parse_nmap_output(self):
        output = """Starting Nmap 7.92 ( https://nmap.org )
Nmap scan report for router.local (192.168.1.1)
Host is up (0.0010s latency).
MAC Address: AA:BB:CC:DD:EE:01 (Generic Vendor)

Nmap scan report for 192.168.1.100
Host is up (0.0020s latency).
MAC Address: 50:C7:BF:11:22:33 (TP-Link)

Nmap done: 256 IP addresses (2 hosts up) scanned in 3.14 seconds"""
        scanner = _make_scanner()
        devices = scanner._parse_nmap_output(output)
        assert len(devices) == 2
        assert devices[0].ip_address == "192.168.1.1"
        assert devices[0].mac_address == "aa:bb:cc:dd:ee:01"
        assert devices[0].hostname == "router.local"
        assert devices[0].vendor == "Generic Vendor"
        assert devices[1].ip_address == "192.168.1.100"
        assert devices[1].vendor == "TP-Link"

    def test_parse_ip_neigh(self):
        output = """192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:01 REACHABLE
192.168.1.50 dev eth0 lladdr 11:22:33:44:55:66 STALE
192.168.1.200 dev eth0  FAILED"""
        scanner = _make_scanner()
        devices = scanner._parse_ip_neigh(output, "2026-04-01T00:00:00Z")
        assert len(devices) == 2
        assert devices[0].ip_address == "192.168.1.1"
        assert devices[1].ip_address == "192.168.1.50"

    def test_parse_arp_a(self):
        output = """router (192.168.1.1) at aa:bb:cc:dd:ee:01 [ether] on eth0
? (192.168.1.50) at 11:22:33:44:55:66 [ether] on eth0"""
        scanner = _make_scanner()
        devices = scanner._parse_arp_a(output, "2026-04-01T00:00:00Z")
        assert len(devices) == 2
        assert devices[0].hostname == "router"
        assert devices[1].hostname == ""  # "?" becomes ""

    def test_classify_known_device(self):
        scanner = _make_scanner(known_macs={"aa:bb:cc:dd:ee:ff"})
        device = DiscoveredDevice(ip_address="192.168.1.10", mac_address="AA:BB:CC:DD:EE:FF")
        scanner.classify_device(device)
        assert device.device_class == DeviceClassification.KNOWN
        assert device.risk_score == 1

    def test_classify_iot_device(self):
        # 50:c7:bf is TP-Link prefix
        scanner = _make_scanner()
        device = DiscoveredDevice(ip_address="192.168.1.10", mac_address="50:c7:bf:11:22:33")
        scanner.classify_device(device)
        assert device.device_class == DeviceClassification.IOT
        assert device.vendor == "TP-Link"
        assert device.risk_score == 2

    def test_classify_unknown_device(self):
        scanner = _make_scanner()
        device = DiscoveredDevice(ip_address="192.168.1.10", mac_address="ff:ee:dd:cc:bb:aa")
        scanner.classify_device(device)
        assert device.device_class == DeviceClassification.UNKNOWN
        assert device.risk_score == 4

    def test_classify_unknown_with_suspicious_ports(self):
        scanner = _make_scanner()
        device = DiscoveredDevice(
            ip_address="192.168.1.10",
            mac_address="ff:ee:dd:cc:bb:aa",
            open_ports=[22, 80, 443],
        )
        scanner.classify_device(device)
        assert device.risk_score == 5

    def test_unknown_devices(self):
        scanner = _make_scanner(known_macs={"aa:bb:cc:dd:ee:ff"})
        scanner._update_history([
            DiscoveredDevice(ip_address="192.168.1.10", mac_address="aa:bb:cc:dd:ee:ff"),
            DiscoveredDevice(ip_address="192.168.1.11", mac_address="11:22:33:44:55:66"),
        ])
        unknown = scanner.unknown_devices()
        assert len(unknown) == 1
        assert unknown[0].mac_address == "11:22:33:44:55:66"

    def test_summary(self):
        scanner = _make_scanner()
        s = scanner.summary()
        assert s["total_scans"] == 0
        assert s["subnet"] == "192.168.1.0/24"

    def test_history_tracking(self):
        scanner = _make_scanner()
        devices = [
            DiscoveredDevice(ip_address="192.168.1.10", mac_address="aa:bb:cc:dd:ee:ff"),
        ]
        scanner._update_history(devices)
        assert len(scanner.history()) == 1
        # Second update should preserve first_seen
        scanner._update_history(devices)
        assert len(scanner.history()) == 1
        h = scanner.history()[0]
        assert h.first_seen  # Should be set


# ========================================================================
# MQTT Broker tests
# ========================================================================

class TestMqttBroker:
    """Tests for MQTT broker client (in-memory mode)."""

    def test_connect_local_mode(self):
        client = MqttBrokerClient()
        assert client.connect()  # Falls back to local mode
        assert client.connected

    def test_publish_and_subscribe(self):
        client = MqttBrokerClient()
        client.connect()

        received: list[MqttMessage] = []
        client.subscribe("test/topic", lambda msg: received.append(msg))
        client.publish("test/topic", "hello")

        assert len(received) == 1
        assert received[0].payload == "hello"
        assert received[0].topic == "test/topic"

    def test_publish_json(self):
        client = MqttBrokerClient()
        client.connect()

        received: list[MqttMessage] = []
        client.subscribe("test/json", lambda msg: received.append(msg))
        client.publish("test/json", {"key": "value"})

        assert len(received) == 1
        data = received[0].payload_json()
        assert data == {"key": "value"}

    def test_wildcard_single_level(self):
        client = MqttBrokerClient()
        client.connect()

        received: list[MqttMessage] = []
        client.subscribe("devices/+/state", lambda msg: received.append(msg))

        client.publish("devices/lamp/state", "on")
        client.publish("devices/plug/state", "off")
        client.publish("devices/lamp/command", "toggle")  # Should NOT match

        assert len(received) == 2

    def test_wildcard_multi_level(self):
        client = MqttBrokerClient()
        client.connect()

        received: list[MqttMessage] = []
        client.subscribe("homelink/#", lambda msg: received.append(msg))

        client.publish("homelink/devices/lamp/state", "on")
        client.publish("homelink/events/anomaly", "{}")
        client.publish("other/topic", "nope")  # Should NOT match

        assert len(received) == 2

    def test_topic_matching(self):
        assert MqttBrokerClient._topic_matches("a/b/c", "a/b/c")
        assert not MqttBrokerClient._topic_matches("a/b/c", "a/b/d")
        assert MqttBrokerClient._topic_matches("a/+/c", "a/b/c")
        assert MqttBrokerClient._topic_matches("a/#", "a/b/c/d")
        assert not MqttBrokerClient._topic_matches("a/b", "a/b/c")

    def test_device_state_helpers(self):
        client = MqttBrokerClient()
        client.connect()

        received: list[MqttMessage] = []
        client.subscribe_device_state("lamp-01", lambda msg: received.append(msg))
        client.publish_device_state("lamp-01", {"status": "on", "brightness": 100})

        assert len(received) == 1
        data = received[0].payload_json()
        assert data["status"] == "on"
        assert "timestamp" in data

    def test_event_helpers(self):
        client = MqttBrokerClient()
        client.connect()

        received: list[MqttMessage] = []
        client.subscribe_events("anomaly", lambda msg: received.append(msg))
        client.publish_event("anomaly", {"type": "new_device"})

        assert len(received) == 1

    def test_message_history(self):
        client = MqttBrokerClient()
        client.connect()
        client.publish("test/1", "a")
        client.publish("test/2", "b")
        history = client.message_history()
        assert len(history) == 2

    def test_stats(self):
        client = MqttBrokerClient()
        client.connect()
        client.publish("test", "data")
        stats = client.stats()
        assert stats["connected"]
        assert stats["messages_published"] == 1

    def test_unsubscribe(self):
        client = MqttBrokerClient()
        client.connect()

        received: list[MqttMessage] = []
        client.subscribe("test/topic", lambda msg: received.append(msg))
        client.publish("test/topic", "first")
        client.unsubscribe("test/topic")
        client.publish("test/topic", "second")

        assert len(received) == 1

    def test_disconnect(self):
        client = MqttBrokerClient()
        client.connect()
        assert client.connected
        client.disconnect()
        assert not client.connected


# ========================================================================
# NetworkMonitor tests
# ========================================================================

class TestNetworkMonitor:
    """Tests for continuous LAN monitoring and anomaly detection."""

    def _make_monitor(self, scanner: NetworkScanner | None = None) -> NetworkMonitor:
        return NetworkMonitor(
            scanner=scanner or _make_scanner(),
            audit=_make_audit(),
            scan_interval_seconds=10,
        )

    def test_init_defaults(self):
        monitor = self._make_monitor()
        assert not monitor.monitoring
        assert monitor.scan_interval == 10

    def test_set_baseline(self):
        monitor = self._make_monitor()
        monitor.set_baseline({"AA:BB:CC:DD:EE:FF"})
        assert "aa:bb:cc:dd:ee:ff" in monitor._baseline_macs

    def test_add_remove_baseline(self):
        monitor = self._make_monitor()
        monitor.add_to_baseline("AA:BB:CC:DD:EE:FF")
        assert "aa:bb:cc:dd:ee:ff" in monitor._baseline_macs
        monitor.remove_from_baseline("AA:BB:CC:DD:EE:FF")
        assert "aa:bb:cc:dd:ee:ff" not in monitor._baseline_macs

    def test_scan_once_no_devices(self):
        """With no nmap/arp available, scan returns empty results."""
        monitor = self._make_monitor()
        anomalies = monitor.scan_once()
        # No devices found = no anomalies
        assert isinstance(anomalies, list)

    def test_new_device_detection(self):
        """Simulate new device appearing on network."""
        monitor = self._make_monitor()
        monitor.set_baseline({"aa:bb:cc:dd:ee:ff"})

        # Manually inject a device into scanner history
        new_device = DiscoveredDevice(
            ip_address="192.168.1.50",
            mac_address="11:22:33:44:55:66",
            vendor="Unknown",
        )
        new_device.risk_score = 4

        # Patch the scanner to return our device
        monitor._scanner.full_scan = lambda: [new_device]  # type: ignore
        anomalies = monitor.scan_once()

        # Should detect new device + high risk
        new_device_anomalies = [
            a for a in anomalies if a.anomaly_type == AnomalyType.NEW_DEVICE
        ]
        assert len(new_device_anomalies) >= 1

    def test_device_offline_detection(self):
        """Detect when a previously online device goes offline."""
        monitor = self._make_monitor()

        # First scan: device present
        device = DiscoveredDevice(
            ip_address="192.168.1.10", mac_address="aa:bb:cc:dd:ee:ff",
        )
        monitor._scanner.full_scan = lambda: [device]  # type: ignore
        monitor.scan_once()

        # Second scan: device gone
        monitor._scanner.full_scan = lambda: []  # type: ignore
        anomalies = monitor.scan_once()

        offline = [a for a in anomalies if a.anomaly_type == AnomalyType.DEVICE_OFFLINE]
        assert len(offline) == 1

    def test_mac_change_detection(self):
        """Detect when an IP's MAC address changes (possible spoofing)."""
        monitor = self._make_monitor()

        # First scan: IP 192.168.1.10 has MAC aa:...
        d1 = DiscoveredDevice(ip_address="192.168.1.10", mac_address="aa:bb:cc:dd:ee:ff")
        monitor._scanner.full_scan = lambda: [d1]  # type: ignore
        monitor.scan_once()

        # Second scan: same IP, different MAC
        d2 = DiscoveredDevice(ip_address="192.168.1.10", mac_address="11:22:33:44:55:66")
        monitor._scanner.full_scan = lambda: [d2]  # type: ignore
        anomalies = monitor.scan_once()

        mac_changes = [a for a in anomalies if a.anomaly_type == AnomalyType.MAC_CHANGE]
        assert len(mac_changes) == 1
        assert mac_changes[0].severity == AlertSeverity.CRITICAL

    def test_anomaly_callback(self):
        """Test that anomaly callbacks fire."""
        monitor = self._make_monitor()
        fired: list[NetworkAnomaly] = []
        monitor.on_anomaly(lambda a: fired.append(a))

        device = DiscoveredDevice(
            ip_address="192.168.1.50", mac_address="11:22:33:44:55:66",
        )
        monitor._scanner.full_scan = lambda: [device]  # type: ignore
        monitor.scan_once()

        assert len(fired) > 0

    def test_acknowledge_anomaly(self):
        monitor = self._make_monitor()
        device = DiscoveredDevice(
            ip_address="192.168.1.50", mac_address="11:22:33:44:55:66",
        )
        monitor._scanner.full_scan = lambda: [device]  # type: ignore
        monitor.scan_once()

        unack = monitor.unacknowledged_anomalies()
        if unack:
            assert monitor.acknowledge_anomaly(0)
            assert monitor.anomalies()[0].acknowledged

    def test_summary(self):
        monitor = self._make_monitor()
        s = monitor.summary()
        assert s["monitoring_active"] is False
        assert s["scan_count"] == 0
        assert "baseline_size" in s

    def test_summary_text(self):
        monitor = self._make_monitor()
        text = monitor.summary_text()
        assert "NETWORK MONITOR" in text
        assert "STOPPED" in text

    def test_device_health_tracking(self):
        monitor = self._make_monitor()
        device = DiscoveredDevice(
            ip_address="192.168.1.10", mac_address="aa:bb:cc:dd:ee:ff",
        )
        monitor._scanner.full_scan = lambda: [device]  # type: ignore
        monitor.scan_once()

        health = monitor.device_health()
        assert len(health) == 1
        assert health[0].is_online

        online = monitor.online_devices()
        assert len(online) == 1

    def test_start_stop_monitoring(self):
        """Test that monitoring thread starts and stops cleanly."""
        monitor = self._make_monitor()
        monitor._scanner.full_scan = lambda: []  # type: ignore

        monitor.start()
        assert monitor.monitoring

        monitor.stop()
        assert not monitor.monitoring


# ========================================================================
# IoT Sentinel agent tests
# ========================================================================

class TestIoTSentinel:
    """Tests for the IoT Sentinel agent lifecycle."""

    def test_init(self):
        sentinel = _make_sentinel()
        assert sentinel.name == "iot_sentinel"

    def test_initialize(self):
        sentinel = _make_sentinel()
        sentinel.initialize()
        # Should connect MQTT in local mode
        assert sentinel.mqtt.connected

    def test_run_no_devices(self):
        sentinel = _make_sentinel()
        sentinel.initialize()
        report = sentinel.run()
        assert report.agent_name == "iot_sentinel"
        assert "Network:" in report.summary
        assert "Risk:" in report.summary

    def test_run_with_anomalies(self):
        sentinel = _make_sentinel()
        sentinel.initialize()

        # Patch scanner to return a new unknown device
        device = DiscoveredDevice(
            ip_address="192.168.1.50",
            mac_address="11:22:33:44:55:66",
            vendor="Unknown",
        )
        device.risk_score = 4
        sentinel.scanner.full_scan = lambda: [device]  # type: ignore
        sentinel.monitor._scanner = sentinel.scanner

        report = sentinel.run()
        assert report.alerts  # Should have critical alerts
        assert report.recommendations  # Should have recommendations

    def test_recommendation_generation(self):
        sentinel = _make_sentinel()
        sentinel.initialize()

        anomaly = NetworkAnomaly(
            anomaly_type=AnomalyType.NEW_DEVICE,
            severity=AlertSeverity.CRITICAL,
            device_ip="192.168.1.50",
            device_mac="11:22:33:44:55:66",
            description="New unknown device",
        )
        rec = sentinel._generate_recommendation(anomaly)
        assert rec is not None
        assert rec["action"] == RecommendationAction.BLOCK
        assert rec["requires_approval"]
        assert not rec["approved"]

    def test_recommendation_mac_change(self):
        sentinel = _make_sentinel()
        sentinel.initialize()

        anomaly = NetworkAnomaly(
            anomaly_type=AnomalyType.MAC_CHANGE,
            severity=AlertSeverity.CRITICAL,
            device_ip="192.168.1.10",
            device_mac="ff:ee:dd:cc:bb:aa",
            description="MAC changed — possible spoofing",
        )
        rec = sentinel._generate_recommendation(anomaly)
        assert rec["action"] == RecommendationAction.BLOCK

    def test_approve_recommendation(self):
        sentinel = _make_sentinel()
        sentinel.initialize()

        # Add a pending recommendation
        sentinel._pending_approvals.append({
            "action": RecommendationAction.BLOCK,
            "description": "Test device",
            "device_ip": "192.168.1.50",
            "device_mac": "11:22:33:44:55:66",
            "reason": "Test",
            "requires_approval": True,
            "approved": False,
        })
        assert sentinel.approve_recommendation(0)
        assert sentinel._pending_approvals[0]["approved"]

    def test_deny_recommendation(self):
        sentinel = _make_sentinel()
        sentinel.initialize()

        sentinel._pending_approvals.append({
            "action": RecommendationAction.ISOLATE,
            "description": "Test device",
            "device_ip": "192.168.1.50",
            "device_mac": "11:22:33:44:55:66",
            "reason": "Test",
            "requires_approval": True,
            "approved": False,
        })
        assert sentinel.deny_recommendation(0)
        assert len(sentinel._pending_approvals) == 0

    def test_pending_approvals(self):
        sentinel = _make_sentinel()
        sentinel.initialize()
        assert len(sentinel.pending_approvals()) == 0

    def test_risk_summary(self):
        sentinel = _make_sentinel()
        sentinel.initialize()

        anomalies = [
            NetworkAnomaly(
                anomaly_type=AnomalyType.NEW_DEVICE,
                severity=AlertSeverity.WARNING,
                description="New device found",
            ),
        ]
        summary = sentinel._build_risk_summary(anomalies)
        assert summary["risk_score"] >= 2
        assert summary["new_unknown_devices"] == 1

    def test_risk_summary_critical(self):
        sentinel = _make_sentinel()
        sentinel.initialize()

        anomalies = [
            NetworkAnomaly(
                anomaly_type=AnomalyType.MAC_CHANGE,
                severity=AlertSeverity.CRITICAL,
                description="MAC spoofing detected",
            ),
        ]
        summary = sentinel._build_risk_summary(anomalies)
        assert summary["risk_score"] == 5

    def test_report(self):
        sentinel = _make_sentinel()
        sentinel.initialize()
        report = sentinel.report()
        assert report.agent_name == "iot_sentinel"

    def test_dashboard_text(self):
        sentinel = _make_sentinel()
        sentinel.initialize()
        text = sentinel.dashboard_text()
        assert "IoT SENTINEL" in text
        assert "SOVEREIGN NETWORK CONTROL" in text
        assert "MQTT BUS" in text

    def test_maintenance_summary(self):
        sentinel = _make_sentinel()
        sentinel.initialize()
        for period in ["daily", "weekly", "monthly"]:
            summary = sentinel.maintenance_summary(period)
            assert summary["period"] == period
            assert "network_status" in summary
            assert "security" in summary

    def test_shutdown(self):
        sentinel = _make_sentinel()
        sentinel.initialize()
        sentinel.shutdown()
        assert not sentinel.mqtt.connected

    def test_mqtt_publishes_on_scan(self):
        sentinel = _make_sentinel()
        sentinel.initialize()

        # Track MQTT messages
        received: list[MqttMessage] = []
        sentinel.mqtt.subscribe("homelink/events/#", lambda msg: received.append(msg))

        sentinel.run()

        # Should have published sentinel_scan event
        scan_events = [m for m in received if "sentinel_scan" in m.topic]
        assert len(scan_events) >= 1


# ========================================================================
# Tailscale tests
# ========================================================================

class TestTailscale:
    """Tests for Tailscale VPN client."""

    def test_init(self):
        client = TailscaleClient()
        # May or may not have tailscale installed
        assert isinstance(client.available, bool)

    def test_parse_peers(self):
        client = TailscaleClient()
        data = {
            "Peer": {
                "key1": {
                    "HostName": "laptop",
                    "TailscaleIPs": ["100.64.0.1"],
                    "OS": "linux",
                    "Online": True,
                    "ExitNode": False,
                    "Relay": "",
                    "LastSeen": "2026-04-01T00:00:00Z",
                    "Tags": [],
                },
                "key2": {
                    "HostName": "phone",
                    "TailscaleIPs": ["100.64.0.2"],
                    "OS": "android",
                    "Online": False,
                    "ExitNode": False,
                    "Relay": "derp1",
                    "LastSeen": "2026-03-31T12:00:00Z",
                    "Tags": ["tag:mobile"],
                },
            }
        }
        client._parse_peers(data)
        peers = client.peers()
        assert len(peers) == 2

        online = client.online_peers()
        assert len(online) == 1
        assert online[0].hostname == "laptop"

    def test_peer_to_dict(self):
        peer = TailscalePeer(
            hostname="test", ip_address="100.64.0.1", os="linux",
        )
        d = peer.to_dict()
        assert d["hostname"] == "test"
        assert d["ip_address"] == "100.64.0.1"

    def test_summary_text(self):
        client = TailscaleClient()
        text = client.summary_text()
        assert "TAILSCALE VPN" in text


# ========================================================================
# Node-RED tests
# ========================================================================

class TestNodeRed:
    """Tests for Node-RED client."""

    def test_init(self):
        client = NodeRedClient()
        assert not client.connected
        assert client.base_url == "http://localhost:1880"

    def test_create_guardian_flows(self):
        client = NodeRedClient()
        flows = client.create_guardian_flows()
        assert len(flows) == 3
        flow_ids = {f.flow_id for f in flows}
        assert "guardian-device-monitor" in flow_ids
        assert "guardian-security-alerts" in flow_ids
        assert "guardian-automation-triggers" in flow_ids

    def test_flow_to_dict(self):
        flow = NodeRedFlow(
            flow_id="test-flow",
            label="Test Flow",
            nodes=[{"id": "n1", "type": "debug"}],
        )
        d = flow.to_dict()
        assert d["id"] == "test-flow"
        assert d["label"] == "Test Flow"
        assert len(d["nodes"]) == 1

    def test_status(self):
        client = NodeRedClient()
        s = client.status()
        assert not s["connected"]
        assert s["flow_count"] == 0

    def test_summary_text(self):
        client = NodeRedClient()
        client.create_guardian_flows()
        text = client.summary_text()
        assert "NODE-RED" in text
        assert "Guardian One" in text


# ========================================================================
# Home Assistant tests
# ========================================================================

class TestHomeAssistant:
    """Tests for Home Assistant client."""

    def test_init(self):
        client = HomeAssistantClient()
        assert not client.connected
        assert client.base_url == "http://homeassistant.local:8123"

    def test_entity_management(self):
        client = HomeAssistantClient()
        entity = HAEntity(
            entity_id="light.bedroom",
            domain=HAEntityDomain.LIGHT,
            friendly_name="Bedroom Light",
            state="on",
        )
        client._entities["light.bedroom"] = entity

        assert client.get_entity("light.bedroom") is not None
        assert client.get_entity("light.nonexistent") is None

    def test_entities_by_domain(self):
        client = HomeAssistantClient()
        client._entities = {
            "light.a": HAEntity(entity_id="light.a", domain=HAEntityDomain.LIGHT),
            "light.b": HAEntity(entity_id="light.b", domain=HAEntityDomain.LIGHT),
            "switch.c": HAEntity(entity_id="switch.c", domain=HAEntityDomain.SWITCH),
        }
        lights = client.entities_by_domain(HAEntityDomain.LIGHT)
        assert len(lights) == 2

    def test_entity_to_dict(self):
        entity = HAEntity(
            entity_id="light.test",
            domain=HAEntityDomain.LIGHT,
            friendly_name="Test Light",
            state="off",
        )
        d = entity.to_dict()
        assert d["entity_id"] == "light.test"
        assert d["domain"] == "light"
        assert d["state"] == "off"

    def test_service_call_to_dict(self):
        call = HAServiceCall(
            domain="light",
            service="turn_on",
            entity_id="light.bedroom",
            data={"brightness": 128},
        )
        d = call.to_dict()
        assert d["domain"] == "light"
        assert d["service"] == "turn_on"
        assert d["data"]["brightness"] == 128

    def test_default_dashboard_modules(self):
        client = HomeAssistantClient()
        modules = client.setup_default_modules()
        assert len(modules) == 3
        module_types = {m.module_type for m in modules}
        assert "room_control" in module_types
        assert "device_groups" in module_types
        assert "security_overview" in module_types

    def test_entity_device_mapping(self):
        client = HomeAssistantClient()
        client._entities["light.bedroom"] = HAEntity(
            entity_id="light.bedroom",
            domain=HAEntityDomain.LIGHT,
        )
        client.map_entity_to_device("light.bedroom", "light-hue-bedroom-01")
        mapped = client.mapped_entities()
        assert mapped["light.bedroom"] == "light-hue-bedroom-01"

    def test_status(self):
        client = HomeAssistantClient()
        s = client.status()
        assert not s["connected"]
        assert s["entity_count"] == 0

    def test_connect_no_token(self):
        client = HomeAssistantClient()
        assert not client.connect()  # No token = fails gracefully


# ========================================================================
# Integration tests
# ========================================================================

class TestIntegration:
    """End-to-end integration tests."""

    def test_sentinel_with_mqtt_and_monitor(self):
        """Test full data flow: scan -> anomaly -> MQTT -> recommendation."""
        sentinel = _make_sentinel()
        sentinel.initialize()

        # Track all MQTT events
        events: list[MqttMessage] = []
        sentinel.mqtt.subscribe("homelink/#", lambda msg: events.append(msg))

        # Inject a suspicious device
        device = DiscoveredDevice(
            ip_address="192.168.1.99",
            mac_address="ff:ee:dd:cc:bb:aa",
            vendor="Unknown",
        )
        device.risk_score = 5
        sentinel.scanner.full_scan = lambda: [device]  # type: ignore
        sentinel.monitor._scanner = sentinel.scanner

        report = sentinel.run()

        # Verify end-to-end flow
        assert report.alerts  # Critical alerts generated
        assert report.recommendations  # Recommendations generated
        assert sentinel.pending_approvals()  # Pending user approval

        # MQTT events should include anomaly + scan result
        anomaly_events = [e for e in events if "anomaly" in e.topic]
        assert len(anomaly_events) >= 1

    def test_sentinel_approve_deny_flow(self):
        """Test the human-in-the-loop approval flow."""
        sentinel = _make_sentinel()
        sentinel.initialize()

        # Add pending recommendations
        sentinel._pending_approvals.extend([
            {
                "action": RecommendationAction.BLOCK,
                "description": "Block rogue device",
                "device_ip": "192.168.1.99",
                "device_mac": "ff:ee:dd:cc:bb:aa",
                "reason": "High risk unknown",
                "requires_approval": True,
                "approved": False,
            },
            {
                "action": RecommendationAction.ISOLATE,
                "description": "Isolate new IoT device",
                "device_ip": "192.168.1.50",
                "device_mac": "50:c7:bf:11:22:33",
                "reason": "New TP-Link device",
                "requires_approval": True,
                "approved": False,
            },
        ])

        # Approve first (index 0), deny second (index 1)
        assert sentinel.approve_recommendation(0)
        assert len(sentinel.pending_approvals()) == 1  # Only second remains pending
        assert sentinel.deny_recommendation(1)  # Second item is at index 1
        assert len(sentinel.pending_approvals()) == 0

    def test_network_monitor_with_mqtt_events(self):
        """Test that network monitor anomalies flow to MQTT via sentinel."""
        sentinel = _make_sentinel()
        sentinel.initialize()

        mqtt_anomalies: list[MqttMessage] = []
        sentinel.mqtt.subscribe(
            "homelink/events/anomaly",
            lambda msg: mqtt_anomalies.append(msg),
        )

        # Simulate new device scan
        device = DiscoveredDevice(
            ip_address="192.168.1.42",
            mac_address="de:ad:be:ef:00:01",
        )
        sentinel.scanner.full_scan = lambda: [device]  # type: ignore
        sentinel.monitor._scanner = sentinel.scanner

        sentinel.run()

        # Anomalies should have been published to MQTT
        assert len(mqtt_anomalies) >= 1
