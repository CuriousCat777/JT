"""IoT Stack — n8n workflow templates and Node-RED flow generators.

Provides pre-built workflow definitions for the AI agent layer:
    - Network Monitor: periodic LAN scan, diff against known devices
    - Risk Summarizer: feed logs to LLM, produce plain-language summaries
    - Recommendation Engine: anomaly → structured action (block/isolate/ignore)

Also generates Node-RED flow JSON for deterministic MQTT-based automations.

These are exportable JSON templates — they do not call n8n or Node-RED
APIs directly. Import them via the respective UIs or API.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# n8n Workflow Templates
# ---------------------------------------------------------------------------

def network_monitor_workflow(
    scan_interval_minutes: int = 5,
    subnet: str = "192.168.1.0/24",
) -> dict[str, Any]:
    """Generate an n8n workflow JSON for periodic network monitoring.

    Workflow:
        1. Cron trigger (every N minutes)
        2. Execute nmap scan via command node
        3. Compare against previous device list
        4. Output: "new device detected" alert
    """
    return {
        "name": "Guardian IoT — Network Monitor",
        "nodes": [
            {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "minutes", "minutesInterval": scan_interval_minutes}]
                    },
                },
                "name": "Schedule Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [250, 300],
            },
            {
                "parameters": {
                    "command": f"nmap -sn {subnet} -oX -",
                },
                "name": "LAN Scan",
                "type": "n8n-nodes-base.executeCommand",
                "typeVersion": 1,
                "position": [470, 300],
            },
            {
                "parameters": {
                    "jsCode": (
                        "const xml = $input.first().json.stdout;\n"
                        "// Parse nmap XML output for hosts\n"
                        "const hosts = [];\n"
                        "const hostMatches = xml.match(/<host>.*?<\\/host>/gs) || [];\n"
                        "for (const h of hostMatches) {\n"
                        "  const ip = h.match(/addr=\"([\\d.]+)\".*?addrtype=\"ipv4\"/);\n"
                        "  const mac = h.match(/addr=\"([A-F0-9:]+)\".*?addrtype=\"mac\"/);\n"
                        "  const vendor = h.match(/vendor=\"([^\"]+)\"/);\n"
                        "  if (ip) hosts.push({\n"
                        "    ip: ip[1],\n"
                        "    mac: mac ? mac[1] : '',\n"
                        "    vendor: vendor ? vendor[1] : 'unknown',\n"
                        "    timestamp: new Date().toISOString()\n"
                        "  });\n"
                        "}\n"
                        "return hosts.map(h => ({json: h}));\n"
                    ),
                },
                "name": "Parse Scan Results",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [690, 300],
            },
            {
                "parameters": {
                    "jsCode": (
                        "// Compare against known device list\n"
                        "const knownFile = '/home/node/.n8n/known_devices.json';\n"
                        "const fs = require('fs');\n"
                        "let known = [];\n"
                        "try { known = JSON.parse(fs.readFileSync(knownFile)); } catch(e) {}\n"
                        "const knownMacs = new Set(known.map(d => d.mac));\n"
                        "const current = $input.all().map(i => i.json);\n"
                        "const newDevices = current.filter(d => d.mac && !knownMacs.has(d.mac));\n"
                        "// Save current as known for next cycle\n"
                        "fs.writeFileSync(knownFile, JSON.stringify(current, null, 2));\n"
                        "if (newDevices.length === 0) {\n"
                        "  return [{json: {alert: false, message: 'No new devices'}}];\n"
                        "}\n"
                        "return newDevices.map(d => ({json: {\n"
                        "  alert: true,\n"
                        "  message: `NEW DEVICE: ${d.ip} (${d.mac}) - ${d.vendor}`,\n"
                        "  device: d\n"
                        "}}));\n"
                    ),
                },
                "name": "Detect New Devices",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [910, 300],
            },
        ],
        "connections": {
            "Schedule Trigger": {"main": [[{"node": "LAN Scan", "type": "main", "index": 0}]]},
            "LAN Scan": {"main": [[{"node": "Parse Scan Results", "type": "main", "index": 0}]]},
            "Parse Scan Results": {"main": [[{"node": "Detect New Devices", "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
        "meta": {
            "templateCreatedBy": "Guardian One — H.O.M.E. L.I.N.K.",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    }


def risk_summarizer_workflow(
    llm_provider: str = "ollama",
    ollama_model: str = "llama3",
) -> dict[str, Any]:
    """Generate an n8n workflow for AI-powered risk summarization.

    Workflow:
        1. Webhook trigger (receives log data)
        2. Format log context
        3. Send to LLM (Ollama or OpenAI)
        4. Output: plain-language risk summary
    """
    llm_node: dict[str, Any]
    if llm_provider == "ollama":
        llm_node = {
            "parameters": {
                "url": f"http://ollama:11434/api/generate",
                "method": "POST",
                "sendBody": True,
                "bodyParameters": {
                    "parameters": [
                        {"name": "model", "value": ollama_model},
                        {
                            "name": "prompt",
                            "value": (
                                "You are a network security analyst for a home IoT system. "
                                "Analyze the following log data and produce a concise, "
                                "plain-language summary of any risks or anomalies. "
                                "Be specific about which devices and what actions to take.\n\n"
                                "Log data:\n{{ $json.log_context }}"
                            ),
                        },
                        {"name": "stream", "value": False},
                    ],
                },
            },
            "name": "LLM Risk Analysis",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [690, 300],
        }
    else:
        llm_node = {
            "parameters": {
                "resource": "chat",
                "model": "gpt-4o-mini",
                "messages": {
                    "values": [
                        {
                            "content": (
                                "You are a network security analyst for a home IoT system. "
                                "Analyze the following log data and produce a concise, "
                                "plain-language summary of any risks or anomalies.\n\n"
                                "Log data:\n{{ $json.log_context }}"
                            ),
                        },
                    ],
                },
            },
            "name": "LLM Risk Analysis",
            "type": "n8n-nodes-base.openAi",
            "typeVersion": 1,
            "position": [690, 300],
        }

    return {
        "name": "Guardian IoT — Risk Summarizer",
        "nodes": [
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "iot-risk-summary",
                },
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [250, 300],
            },
            {
                "parameters": {
                    "jsCode": (
                        "const data = $input.first().json.body || $input.first().json;\n"
                        "const logContext = JSON.stringify(data, null, 2);\n"
                        "return [{json: {log_context: logContext, received_at: new Date().toISOString()}}];\n"
                    ),
                },
                "name": "Format Context",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [470, 300],
            },
            llm_node,
            {
                "parameters": {
                    "jsCode": (
                        "const response = $input.first().json;\n"
                        "const summary = response.response || response.choices?.[0]?.message?.content || 'No analysis';\n"
                        "return [{json: {\n"
                        "  summary: summary,\n"
                        "  analyzed_at: new Date().toISOString(),\n"
                        "  source: 'guardian_iot_risk_summarizer'\n"
                        "}}];\n"
                    ),
                },
                "name": "Format Output",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [910, 300],
            },
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Format Context", "type": "main", "index": 0}]]},
            "Format Context": {"main": [[{"node": "LLM Risk Analysis", "type": "main", "index": 0}]]},
            "LLM Risk Analysis": {"main": [[{"node": "Format Output", "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
        "meta": {
            "templateCreatedBy": "Guardian One — H.O.M.E. L.I.N.K.",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    }


def recommendation_engine_workflow(
    llm_provider: str = "ollama",
    ollama_model: str = "llama3",
) -> dict[str, Any]:
    """Generate an n8n workflow for AI-powered security recommendations.

    Workflow:
        1. Webhook trigger (receives anomaly data)
        2. LLM produces structured recommendation: {action, confidence, reason}
        3. Filter: only forward if confidence > threshold
        4. Send notification to Home Assistant
    """
    return {
        "name": "Guardian IoT — Recommendation Engine",
        "nodes": [
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": "iot-recommend",
                },
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [250, 300],
            },
            {
                "parameters": {
                    "url": "http://ollama:11434/api/generate",
                    "method": "POST",
                    "sendBody": True,
                    "bodyParameters": {
                        "parameters": [
                            {"name": "model", "value": ollama_model},
                            {
                                "name": "prompt",
                                "value": (
                                    "You are a network security AI for a home IoT system. "
                                    "Given the following anomaly, respond with ONLY a JSON object:\n"
                                    '{"action": "block_device|isolate_vlan|ignore", '
                                    '"confidence": 0.0-1.0, '
                                    '"reason": "brief explanation"}\n\n'
                                    "Anomaly:\n{{ $json.body ? JSON.stringify($json.body) : JSON.stringify($json) }}\n\n"
                                    "Rules:\n"
                                    "- block_device: device is actively malicious\n"
                                    "- isolate_vlan: unknown or suspicious, needs investigation\n"
                                    "- ignore: benign activity or known device\n"
                                    "Respond with JSON only."
                                ),
                            },
                            {"name": "stream", "value": False},
                        ],
                    },
                },
                "name": "LLM Recommendation",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [470, 300],
            },
            {
                "parameters": {
                    "jsCode": (
                        "const raw = $input.first().json.response || '';\n"
                        "let rec;\n"
                        "try {\n"
                        "  const jsonMatch = raw.match(/\\{[\\s\\S]*\\}/);\n"
                        "  rec = JSON.parse(jsonMatch ? jsonMatch[0] : raw);\n"
                        "} catch(e) {\n"
                        "  rec = {action: 'ignore', confidence: 0, reason: 'Failed to parse LLM output'};\n"
                        "}\n"
                        "rec.analyzed_at = new Date().toISOString();\n"
                        "rec.execution_policy = 'user_approval_required';\n"
                        "return [{json: rec}];\n"
                    ),
                },
                "name": "Parse Recommendation",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [690, 300],
            },
            {
                "parameters": {
                    "conditions": {
                        "number": [
                            {
                                "value1": "={{ $json.confidence }}",
                                "operation": "largerEqual",
                                "value2": 0.7,
                            },
                        ],
                    },
                },
                "name": "Confidence Filter",
                "type": "n8n-nodes-base.filter",
                "typeVersion": 2,
                "position": [910, 300],
            },
            {
                "parameters": {
                    "url": "http://homeassistant:8123/api/services/notify/persistent_notification",
                    "method": "POST",
                    "sendBody": True,
                    "bodyParameters": {
                        "parameters": [
                            {
                                "name": "message",
                                "value": "IoT Alert: {{ $json.action }} — {{ $json.reason }} (confidence: {{ $json.confidence }})",
                            },
                            {"name": "title", "value": "Guardian One IoT"},
                        ],
                    },
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": "Bearer {{ $env.HA_TOKEN }}"},
                            {"name": "Content-Type", "value": "application/json"},
                        ],
                    },
                },
                "name": "Notify Home Assistant",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [1130, 300],
            },
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "LLM Recommendation", "type": "main", "index": 0}]]},
            "LLM Recommendation": {"main": [[{"node": "Parse Recommendation", "type": "main", "index": 0}]]},
            "Parse Recommendation": {"main": [[{"node": "Confidence Filter", "type": "main", "index": 0}]]},
            "Confidence Filter": {"main": [[{"node": "Notify Home Assistant", "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
        "meta": {
            "templateCreatedBy": "Guardian One — H.O.M.E. L.I.N.K.",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Node-RED Flow Templates
# ---------------------------------------------------------------------------

def nodered_security_flow() -> dict[str, Any]:
    """Generate a Node-RED flow for MQTT-based security automation.

    Flow:
        1. MQTT in: subscribe to home/security/#
        2. Function node: parse anomaly
        3. Switch: route by severity
        4. Notify user + optionally disable device
    """
    return {
        "id": "guardian_iot_security",
        "label": "Guardian IoT Security",
        "nodes": [
            {
                "id": "mqtt_in_1",
                "type": "mqtt in",
                "name": "Security Events",
                "topic": "home/security/#",
                "broker": "mqtt_broker_1",
                "qos": "1",
                "x": 150,
                "y": 200,
                "wires": [["parse_1"]],
            },
            {
                "id": "parse_1",
                "type": "function",
                "name": "Parse Anomaly",
                "func": (
                    "let data;\n"
                    "try { data = JSON.parse(msg.payload); } catch(e) { data = {event: msg.payload}; }\n"
                    "msg.anomaly = data;\n"
                    "msg.severity = data.severity || 'medium';\n"
                    "msg.device_id = data.device_id || 'unknown';\n"
                    "return msg;\n"
                ),
                "x": 350,
                "y": 200,
                "wires": [["switch_1"]],
            },
            {
                "id": "switch_1",
                "type": "switch",
                "name": "By Severity",
                "property": "severity",
                "rules": [
                    {"t": "eq", "v": "critical"},
                    {"t": "eq", "v": "high"},
                    {"t": "else"},
                ],
                "x": 550,
                "y": 200,
                "wires": [["alert_critical"], ["alert_high"], ["log_1"]],
            },
            {
                "id": "alert_critical",
                "type": "function",
                "name": "Critical Alert",
                "func": (
                    "msg.payload = {\n"
                    "  title: 'CRITICAL IoT Alert',\n"
                    "  message: `Device ${msg.device_id}: ${msg.anomaly.event || 'anomaly detected'}`,\n"
                    "  action_required: true\n"
                    "};\n"
                    "return msg;\n"
                ),
                "x": 750,
                "y": 120,
                "wires": [["mqtt_out_1"]],
            },
            {
                "id": "alert_high",
                "type": "function",
                "name": "High Alert",
                "func": (
                    "msg.payload = {\n"
                    "  title: 'HIGH IoT Alert',\n"
                    "  message: `Device ${msg.device_id}: ${msg.anomaly.event || 'anomaly detected'}`,\n"
                    "  action_required: false\n"
                    "};\n"
                    "return msg;\n"
                ),
                "x": 750,
                "y": 200,
                "wires": [["mqtt_out_1"]],
            },
            {
                "id": "log_1",
                "type": "debug",
                "name": "Log Medium/Low",
                "active": True,
                "x": 750,
                "y": 280,
                "wires": [],
            },
            {
                "id": "mqtt_out_1",
                "type": "mqtt out",
                "name": "Alert Output",
                "topic": "home/alerts/iot",
                "broker": "mqtt_broker_1",
                "qos": "1",
                "x": 950,
                "y": 160,
                "wires": [],
            },
            {
                "id": "mqtt_broker_1",
                "type": "mqtt-broker",
                "name": "Local Mosquitto",
                "broker": "mosquitto",
                "port": "1883",
            },
        ],
        "meta": {
            "createdBy": "Guardian One — H.O.M.E. L.I.N.K.",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    }


def nodered_device_offline_flow() -> dict[str, Any]:
    """Generate a Node-RED flow for device offline detection.

    Flow:
        1. Inject trigger (periodic)
        2. Function: check last-seen timestamps
        3. Alert if device has been offline > threshold
    """
    return {
        "id": "guardian_iot_offline",
        "label": "Guardian IoT Offline Detector",
        "nodes": [
            {
                "id": "inject_1",
                "type": "inject",
                "name": "Every 5 min",
                "repeat": "300",
                "x": 150,
                "y": 200,
                "wires": [["check_offline"]],
            },
            {
                "id": "check_offline",
                "type": "function",
                "name": "Check Offline Devices",
                "func": (
                    "// Read device registry from MQTT retained messages\n"
                    "// or from a local state file\n"
                    "const threshold_ms = 10 * 60 * 1000; // 10 minutes\n"
                    "const now = Date.now();\n"
                    "const devices = flow.get('device_registry') || {};\n"
                    "const offline = [];\n"
                    "for (const [id, dev] of Object.entries(devices)) {\n"
                    "  if (dev.last_seen && (now - dev.last_seen) > threshold_ms) {\n"
                    "    offline.push({device_id: id, last_seen: new Date(dev.last_seen).toISOString()});\n"
                    "  }\n"
                    "}\n"
                    "if (offline.length > 0) {\n"
                    "  msg.payload = {event: 'devices_offline', devices: offline, count: offline.length};\n"
                    "  return msg;\n"
                    "}\n"
                    "return null; // No offline devices\n"
                ),
                "x": 380,
                "y": 200,
                "wires": [["mqtt_out_offline"]],
            },
            {
                "id": "mqtt_out_offline",
                "type": "mqtt out",
                "name": "Offline Alert",
                "topic": "home/alerts/offline",
                "broker": "mqtt_broker_2",
                "qos": "1",
                "x": 600,
                "y": 200,
                "wires": [],
            },
            {
                "id": "mqtt_broker_2",
                "type": "mqtt-broker",
                "name": "Local Mosquitto",
                "broker": "mosquitto",
                "port": "1883",
            },
        ],
        "meta": {
            "createdBy": "Guardian One — H.O.M.E. L.I.N.K.",
            "createdAt": datetime.now(timezone.utc).isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Export all workflows as importable JSON
# ---------------------------------------------------------------------------

def export_all_workflows(output_dir: str = ".") -> dict[str, str]:
    """Write all workflow templates to JSON files for import.

    Returns a dict mapping filename → path.
    """
    from pathlib import Path

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    files = {}

    # n8n workflows
    n8n_workflows = {
        "n8n_network_monitor.json": network_monitor_workflow(),
        "n8n_risk_summarizer.json": risk_summarizer_workflow(),
        "n8n_recommendation_engine.json": recommendation_engine_workflow(),
    }
    for name, workflow in n8n_workflows.items():
        path = out / name
        path.write_text(json.dumps(workflow, indent=2))
        files[name] = str(path)

    # Node-RED flows
    nodered_flows = {
        "nodered_security_flow.json": nodered_security_flow(),
        "nodered_device_offline_flow.json": nodered_device_offline_flow(),
    }
    for name, flow in nodered_flows.items():
        path = out / name
        path.write_text(json.dumps(flow, indent=2))
        files[name] = str(path)

    return files
