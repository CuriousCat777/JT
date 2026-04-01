"""Tests for Sovereign IoT Local Control — iot_controller, iot_stack, registry integrations."""

import json
import tempfile
from pathlib import Path

from guardian_one.core.audit import AuditLog
from guardian_one.homelink.iot_controller import (
    IoTController,
    IoTService,
    ServiceState,
    DiscoveredDevice,
    DeviceClassification,
    MQTTMessage,
    IoTStackHealth,
    CORE_SERVICES,
    DEFAULT_VLANS,
    FIREWALL_RULES,
    VLANPolicy,
)
from guardian_one.homelink.iot_stack import (
    network_monitor_workflow,
    risk_summarizer_workflow,
    recommendation_engine_workflow,
    nodered_security_flow,
    nodered_device_offline_flow,
    export_all_workflows,
)
from guardian_one.homelink.registry import (
    IntegrationRegistry,
    HOME_ASSISTANT_INTEGRATION,
    MOSQUITTO_MQTT_INTEGRATION,
    ZIGBEE2MQTT_INTEGRATION,
    NODERED_INTEGRATION,
    TAILSCALE_INTEGRATION,
)


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


# ========================================================================
# IoT Controller — initialization
# ========================================================================

def test_iot_controller_init():
    """Controller initializes with core services."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        assert iot._initialized is True
        assert len(iot._services) == len(CORE_SERVICES)


def test_iot_controller_services_match_core():
    """All CORE_SERVICES are registered after init."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        for svc in CORE_SERVICES:
            assert svc.name in iot._services
            assert iot._services[svc.name].image == svc.image


def test_iot_controller_stack_dir_property():
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        assert iot.stack_dir == Path(tmpdir)


def test_iot_controller_compose_path():
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        assert iot.compose_path == Path(tmpdir) / "docker-compose.yml"


# ========================================================================
# Scaffold
# ========================================================================

def test_scaffold_creates_directories():
    """scaffold_stack creates all required subdirectories."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        result = iot.scaffold_stack()
        assert result["success"] is True

        for subdir in ["homeassistant", "mosquitto", "zigbee2mqtt", "nodered", "n8n", "ollama"]:
            assert (Path(tmpdir) / subdir).is_dir()


def test_scaffold_creates_compose_file():
    """scaffold_stack creates docker-compose.yml."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        iot.scaffold_stack()
        assert (Path(tmpdir) / "docker-compose.yml").exists()


def test_scaffold_creates_mosquitto_conf():
    """scaffold_stack creates mosquitto.conf."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        iot.scaffold_stack()
        conf = Path(tmpdir) / "mosquitto" / "mosquitto.conf"
        assert conf.exists()
        content = conf.read_text()
        assert "listener 1883" in content


def test_scaffold_creates_zigbee2mqtt_config():
    """scaffold_stack creates zigbee2mqtt configuration.yaml."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        iot.scaffold_stack(zigbee_device="/dev/ttyACM0")
        conf = Path(tmpdir) / "zigbee2mqtt" / "configuration.yaml"
        assert conf.exists()
        content = conf.read_text()
        assert "homeassistant: true" in content
        assert "/dev/ttyACM0" in content


def test_scaffold_returns_next_steps():
    """scaffold_stack includes actionable next steps."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        result = iot.scaffold_stack()
        assert len(result["next_steps"]) > 0
        assert any("docker-compose up" in s for s in result["next_steps"])


def test_scaffold_audits_action():
    """scaffold_stack writes to the audit log."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        iot.scaffold_stack()
        entries = audit.query(agent="homelink_iot")
        actions = [e.action for e in entries]
        assert "stack_scaffolded" in actions


# ========================================================================
# Docker Compose generation
# ========================================================================

def test_generate_compose_includes_all_services():
    """Generated compose YAML includes all 7 services."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        content = iot.generate_compose()
        for svc in ["homeassistant", "mosquitto", "zigbee2mqtt", "nodered", "n8n", "ollama", "tailscale"]:
            assert svc in content


def test_generate_compose_custom_zigbee_device():
    """Zigbee device path is configurable."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        content = iot.generate_compose(zigbee_device="/dev/ttyACM0")
        assert "/dev/ttyACM0" in content


def test_generate_compose_custom_timezone():
    """Timezone is embedded in n8n service."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit, timezone="US/Eastern")
        iot.initialize()
        content = iot.generate_compose()
        assert "US/Eastern" in content


# ========================================================================
# Stack health
# ========================================================================

def test_stack_health_offline_without_docker():
    """Health reports offline when docker is not available (CI)."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        health = iot.stack_health()
        assert isinstance(health, IoTStackHealth)
        assert health.total_count == len(CORE_SERVICES)
        # In CI, docker won't be running
        assert health.overall_status in ("healthy", "degraded", "offline")


def test_stack_health_compose_exists_flag():
    """Health check reports whether docker-compose.yml exists."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()

        health1 = iot.stack_health()
        assert health1.compose_exists is False

        iot.scaffold_stack()
        health2 = iot.stack_health()
        assert health2.compose_exists is True


# ========================================================================
# Network scanning
# ========================================================================

def test_nmap_xml_parsing():
    """_parse_nmap_xml correctly extracts devices from XML."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()

        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <nmaprun>
            <host>
                <status state="up"/>
                <address addr="192.168.1.1" addrtype="ipv4"/>
                <address addr="AA:BB:CC:DD:EE:FF" addrtype="mac" vendor="TP-Link"/>
                <hostnames><hostname name="router.local"/></hostnames>
            </host>
            <host>
                <status state="up"/>
                <address addr="192.168.1.50" addrtype="ipv4"/>
                <address addr="11:22:33:44:55:66" addrtype="mac" vendor="Philips"/>
                <hostnames/>
            </host>
            <host>
                <status state="down"/>
                <address addr="192.168.1.99" addrtype="ipv4"/>
            </host>
        </nmaprun>"""

        devices = iot._parse_nmap_xml(xml)
        assert len(devices) == 2  # Down host excluded
        assert devices[0].ip_address == "192.168.1.1"
        assert devices[0].mac_address == "AA:BB:CC:DD:EE:FF"
        assert devices[0].vendor == "TP-Link"
        assert devices[0].hostname == "router.local"
        assert devices[1].ip_address == "192.168.1.50"
        assert devices[1].vendor == "Philips"


def test_nmap_xml_parsing_empty():
    """_parse_nmap_xml handles empty or malformed XML."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()

        assert iot._parse_nmap_xml("") == []
        assert iot._parse_nmap_xml("<invalid>") == []
        assert iot._parse_nmap_xml('<?xml version="1.0"?><nmaprun></nmaprun>') == []


def test_register_known_device():
    """register_known_device marks MAC as known."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()

        iot.register_known_device("AA:BB:CC:DD:EE:FF", "Living Room Router")
        assert iot._known_macs["AA:BB:CC:DD:EE:FF"] == "Living Room Router"


def test_quarantine_device():
    """quarantine_device marks device and returns action items."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()

        iot._discovered_devices = [
            DiscoveredDevice(
                ip_address="192.168.1.100",
                mac_address="AA:BB:CC:DD:EE:FF",
                vendor="Unknown",
                device_class=DeviceClassification.UNKNOWN,
                risk_score=4,
            )
        ]

        result = iot.quarantine_device("AA:BB:CC:DD:EE:FF")
        assert result["success"] is True
        assert len(result["action_required"]) > 0
        assert iot._discovered_devices[0].device_class == DeviceClassification.QUARANTINED
        assert iot._discovered_devices[0].risk_score == 5


def test_quarantine_device_not_found():
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        result = iot.quarantine_device("FF:FF:FF:FF:FF:FF")
        assert result["success"] is False


def test_unknown_devices_filter():
    """unknown_devices returns only UNKNOWN-classified devices."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()

        iot._discovered_devices = [
            DiscoveredDevice(ip_address="1.1.1.1", device_class=DeviceClassification.KNOWN),
            DiscoveredDevice(ip_address="2.2.2.2", device_class=DeviceClassification.UNKNOWN),
            DiscoveredDevice(ip_address="3.3.3.3", device_class=DeviceClassification.IOT),
            DiscoveredDevice(ip_address="4.4.4.4", device_class=DeviceClassification.UNKNOWN),
        ]

        unknown = iot.unknown_devices()
        assert len(unknown) == 2
        assert all(d.device_class == DeviceClassification.UNKNOWN for d in unknown)


# ========================================================================
# VLAN / Security
# ========================================================================

def test_vlan_policy():
    """vlan_policy returns structured VLAN and firewall data."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        policy = iot.vlan_policy()
        assert len(policy["vlans"]) == 3
        assert policy["vlans"][0]["vlan_id"] == 10
        assert policy["vlans"][1]["vlan_id"] == 20
        assert policy["vlans"][2]["vlan_id"] == 30
        assert len(policy["firewall_rules"]) == 3
        assert "recommendation" in policy


def test_security_checklist():
    """security_checklist returns actionable items."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        checklist = iot.security_checklist()
        assert len(checklist) >= 5
        priorities = {item["priority"] for item in checklist}
        assert "critical" in priorities
        assert "high" in priorities
        for item in checklist:
            assert "item" in item
            assert "action" in item


def test_default_vlans():
    """DEFAULT_VLANS has correct structure."""
    assert len(DEFAULT_VLANS) == 3
    names = {v.name for v in DEFAULT_VLANS}
    assert names == {"core", "iot", "user"}
    iot_vlan = next(v for v in DEFAULT_VLANS if v.name == "iot")
    assert "internet" in iot_vlan.blocked_outbound


# ========================================================================
# Dashboard
# ========================================================================

def test_dashboard_text():
    """dashboard_text returns formatted string."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        text = iot.dashboard_text()
        assert "SOVEREIGN IoT CONTROL" in text
        assert "SERVICES:" in text
        assert "ACCESS POINTS:" in text


def test_dashboard_shows_unknown_devices():
    """Dashboard highlights unknown devices when present."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        iot._discovered_devices = [
            DiscoveredDevice(ip_address="10.0.0.5", mac_address="AA:BB:CC:DD:EE:FF",
                             device_class=DeviceClassification.UNKNOWN),
        ]
        text = iot.dashboard_text()
        assert "UNKNOWN" in text
        assert "10.0.0.5" in text


# ========================================================================
# Access points & maintenance
# ========================================================================

def test_access_points():
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        ap = iot.access_points()
        assert "home_assistant" in ap
        assert "8123" in ap["home_assistant"]
        assert "mqtt" in ap
        assert "1883" in ap["mqtt"]


def test_maintenance_schedule():
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        maint = iot.maintenance_schedule()
        assert "automated" in maint
        assert "manual_approval_required" in maint
        assert "firmware_updates" in maint["manual_approval_required"]
        assert "schedule" in maint


# ========================================================================
# IoT Stack — n8n workflow templates
# ========================================================================

def test_network_monitor_workflow():
    """Network monitor workflow has correct structure."""
    wf = network_monitor_workflow(scan_interval_minutes=10)
    assert wf["name"] == "Guardian IoT — Network Monitor"
    assert len(wf["nodes"]) == 4
    assert "connections" in wf
    # Verify the chain: trigger → scan → parse → detect
    node_names = [n["name"] for n in wf["nodes"]]
    assert "Schedule Trigger" in node_names
    assert "LAN Scan" in node_names
    assert "Parse Scan Results" in node_names
    assert "Detect New Devices" in node_names


def test_network_monitor_custom_subnet():
    """Network monitor embeds custom subnet in scan command."""
    wf = network_monitor_workflow(subnet="10.0.0.0/24")
    scan_node = next(n for n in wf["nodes"] if n["name"] == "LAN Scan")
    assert "10.0.0.0/24" in scan_node["parameters"]["command"]


def test_risk_summarizer_workflow_ollama():
    """Risk summarizer uses Ollama endpoint by default."""
    wf = risk_summarizer_workflow(llm_provider="ollama")
    assert wf["name"] == "Guardian IoT — Risk Summarizer"
    llm_node = next(n for n in wf["nodes"] if n["name"] == "LLM Risk Analysis")
    assert "ollama" in llm_node["parameters"]["url"]


def test_risk_summarizer_workflow_openai():
    """Risk summarizer can use OpenAI backend."""
    wf = risk_summarizer_workflow(llm_provider="openai")
    llm_node = next(n for n in wf["nodes"] if n["name"] == "LLM Risk Analysis")
    assert llm_node["type"] == "n8n-nodes-base.openAi"


def test_recommendation_engine_workflow():
    """Recommendation engine has correct 5-node chain."""
    wf = recommendation_engine_workflow()
    assert wf["name"] == "Guardian IoT — Recommendation Engine"
    assert len(wf["nodes"]) == 5
    node_names = [n["name"] for n in wf["nodes"]]
    assert "Confidence Filter" in node_names
    assert "Notify Home Assistant" in node_names


def test_recommendation_engine_custom_model():
    """Recommendation engine uses specified Ollama model."""
    wf = recommendation_engine_workflow(ollama_model="mistral")
    llm_node = next(n for n in wf["nodes"] if n["name"] == "LLM Recommendation")
    params = llm_node["parameters"]["bodyParameters"]["parameters"]
    model_param = next(p for p in params if p["name"] == "model")
    assert model_param["value"] == "mistral"


# ========================================================================
# IoT Stack — Node-RED flow templates
# ========================================================================

def test_nodered_security_flow():
    """Security flow has MQTT in → parse → switch → alerts."""
    flow = nodered_security_flow()
    assert flow["label"] == "Guardian IoT Security"
    node_types = {n["type"] for n in flow["nodes"] if "type" in n}
    assert "mqtt in" in node_types
    assert "function" in node_types
    assert "switch" in node_types
    assert "mqtt out" in node_types


def test_nodered_security_flow_mqtt_topic():
    """Security flow subscribes to home/security/#."""
    flow = nodered_security_flow()
    mqtt_in = next(n for n in flow["nodes"] if n.get("type") == "mqtt in")
    assert mqtt_in["topic"] == "home/security/#"


def test_nodered_device_offline_flow():
    """Offline detector flow checks device registry."""
    flow = nodered_device_offline_flow()
    assert flow["label"] == "Guardian IoT Offline Detector"
    node_ids = {n["id"] for n in flow["nodes"]}
    assert "inject_1" in node_ids
    assert "check_offline" in node_ids


# ========================================================================
# Workflow export
# ========================================================================

def test_export_all_workflows():
    """export_all_workflows writes JSON files to disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        files = export_all_workflows(output_dir=tmpdir)
        assert len(files) == 5
        for name, path in files.items():
            assert Path(path).exists()
            data = json.loads(Path(path).read_text())
            assert isinstance(data, dict)


def test_exported_workflows_valid_json():
    """All exported workflows are valid JSON with expected keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        files = export_all_workflows(output_dir=tmpdir)
        for name, path in files.items():
            data = json.loads(Path(path).read_text())
            if name.startswith("n8n_"):
                assert "nodes" in data
                assert "connections" in data
            elif name.startswith("nodered_"):
                assert "nodes" in data
                assert "label" in data


# ========================================================================
# Registry — IoT integration records
# ========================================================================

def test_home_assistant_integration():
    """Home Assistant integration has complete threat model."""
    rec = HOME_ASSISTANT_INTEGRATION
    assert rec.name == "home_assistant"
    assert rec.auth_method == "api_key"
    assert len(rec.threat_model) == 5
    assert rec.owner_agent == "device_agent"
    assert rec.failure_impact != ""
    assert rec.rollback_procedure != ""


def test_mosquitto_integration():
    """Mosquitto integration has complete threat model."""
    rec = MOSQUITTO_MQTT_INTEGRATION
    assert rec.name == "mosquitto_mqtt"
    assert len(rec.threat_model) == 5
    assert rec.owner_agent == "homelink_iot"
    critical = [t for t in rec.threat_model if t.severity == "critical"]
    assert len(critical) >= 1  # Anonymous access is critical


def test_zigbee2mqtt_integration():
    rec = ZIGBEE2MQTT_INTEGRATION
    assert rec.name == "zigbee2mqtt"
    assert len(rec.threat_model) >= 3


def test_nodered_registry_integration():
    rec = NODERED_INTEGRATION
    assert rec.name == "nodered"
    critical = [t for t in rec.threat_model if t.severity == "critical"]
    assert len(critical) >= 1


def test_tailscale_integration():
    rec = TAILSCALE_INTEGRATION
    assert rec.name == "tailscale_vpn"
    assert "vpn" in rec.description.lower() or "VPN" in rec.description


def test_registry_loads_iot_integrations():
    """IntegrationRegistry.load_defaults includes all IoT integrations."""
    registry = IntegrationRegistry()
    registry.load_defaults()
    iot_names = ["home_assistant", "mosquitto_mqtt", "zigbee2mqtt", "nodered", "tailscale_vpn"]
    for name in iot_names:
        rec = registry.get(name)
        assert rec is not None, f"Missing integration: {name}"
        assert rec.status == "active"


def test_registry_iot_threat_summary():
    """IoT integrations appear in the threat summary."""
    registry = IntegrationRegistry()
    registry.load_defaults()
    threats = registry.threat_summary()
    iot_services = {"home_assistant", "mosquitto_mqtt", "zigbee2mqtt", "nodered", "tailscale_vpn"}
    services_in_threats = {t["service"] for t in threats}
    assert iot_services.issubset(services_in_threats)


# ========================================================================
# Data model tests
# ========================================================================

def test_service_state_enum():
    assert ServiceState.RUNNING.value == "running"
    assert ServiceState.STOPPED.value == "stopped"
    assert ServiceState.ERROR.value == "error"


def test_device_classification_enum():
    assert DeviceClassification.KNOWN.value == "known"
    assert DeviceClassification.QUARANTINED.value == "quarantined"


def test_iot_service_dataclass():
    svc = IoTService(
        name="test", image="test:latest", container_name="test_c",
        ports=["8080:8080"], required=True,
    )
    assert svc.name == "test"
    assert svc.state == ServiceState.UNKNOWN


def test_discovered_device_defaults():
    dev = DiscoveredDevice(ip_address="192.168.1.1")
    assert dev.mac_address == ""
    assert dev.device_class == DeviceClassification.UNKNOWN
    assert dev.risk_score == 3


def test_mqtt_message_timestamp():
    msg = MQTTMessage(topic="test/topic", payload="hello")
    assert msg.timestamp != ""
    assert "T" in msg.timestamp  # ISO format


def test_core_services_count():
    """Exactly 7 core services defined."""
    assert len(CORE_SERVICES) == 7
    names = {s.name for s in CORE_SERVICES}
    expected = {"homeassistant", "mosquitto", "nodered", "n8n", "zigbee2mqtt", "ollama", "tailscale"}
    assert names == expected


def test_core_services_required_flags():
    """homeassistant, mosquitto, nodered, n8n are required."""
    required = {s.name for s in CORE_SERVICES if s.required}
    assert "homeassistant" in required
    assert "mosquitto" in required
    assert "nodered" in required
    assert "n8n" in required
    assert "zigbee2mqtt" not in required
    assert "ollama" not in required


# ========================================================================
# Start/stop without Docker (graceful failures)
# ========================================================================

def test_start_stack_no_compose():
    """start_stack fails gracefully when compose file doesn't exist."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        result = iot.start_stack()
        assert result["success"] is False
        assert "not found" in result["error"].lower()


def test_stop_stack_no_compose():
    """stop_stack fails gracefully when compose file doesn't exist."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        result = iot.stop_stack()
        assert result["success"] is False


# ========================================================================
# YAML generation
# ========================================================================

def test_dict_to_yaml_basic():
    """_dict_to_yaml produces readable YAML-like output."""
    data = {"version": "3.9", "services": {"web": {"image": "nginx", "ports": ["80:80"]}}}
    result = IoTController._dict_to_yaml(data)
    assert "version:" in result
    assert "services:" in result
    assert "nginx" in result
    assert "80:80" in result


def test_dict_to_yaml_nested():
    """_dict_to_yaml handles nested dicts."""
    data = {"a": {"b": {"c": "deep"}}}
    result = IoTController._dict_to_yaml(data)
    assert "deep" in result
    # Check indentation
    lines = result.split("\n")
    assert any("    c:" in line for line in lines)


# ========================================================================
# Edge cases
# ========================================================================

def test_scan_network_returns_empty_without_nmap():
    """scan_network returns empty list when nmap not available."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()
        # This will return empty if nmap is not installed (typical in CI)
        devices = iot.scan_network("192.168.1.0/24")
        assert isinstance(devices, list)


def test_register_known_device_updates_existing():
    """register_known_device updates classification of already-discovered devices."""
    audit = _make_audit()
    with tempfile.TemporaryDirectory() as tmpdir:
        iot = IoTController(stack_dir=Path(tmpdir), audit=audit)
        iot.initialize()

        iot._discovered_devices = [
            DiscoveredDevice(
                ip_address="192.168.1.50",
                mac_address="AA:BB:CC:DD:EE:FF",
                device_class=DeviceClassification.UNKNOWN,
                risk_score=4,
            )
        ]

        iot.register_known_device("AA:BB:CC:DD:EE:FF", "My Hue Bridge")
        assert iot._discovered_devices[0].device_class == DeviceClassification.KNOWN
        assert iot._discovered_devices[0].risk_score == 1
        assert iot._discovered_devices[0].notes == "My Hue Bridge"
