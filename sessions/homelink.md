# Session Handoff: H.O.M.E. L.I.N.K. — Self-Hosted Smart Home AI

> Last updated: 2026-03-19
> Branch: `claude/guardian-one-system-4uvJv`
> Owner: Jeremy Paulo Salvino Tabernero

---

## What This Is (Plain English)

H.O.M.E. L.I.N.K. is Guardian One's **self-hosted smart home brain**. It lives
on YOUR hardware, talks to YOUR devices over YOUR local network, and keeps
everything encrypted. No cloud company sees your data. No subscription fees
control your lights.

Think of it like this:

```
┌──────────────────────────────────────────────────────┐
│  YOUR HOME NETWORK                                    │
│                                                       │
│  ┌─────────────┐    ┌──────────────────────────────┐ │
│  │  Guardian    │    │  Your Devices                │ │
│  │  One AI      │───▶│  Lights, Blinds, Cameras,   │ │
│  │  (this box)  │    │  Plugs, TV, Flipper Zero    │ │
│  └──────┬───────┘    └──────────────────────────────┘ │
│         │                                             │
│  ┌──────┴───────┐    ┌──────────────────────────────┐ │
│  │  Vault       │    │  IoT VLAN (isolated network) │ │
│  │  (encrypted  │    │  Devices CAN'T reach the     │ │
│  │   passwords) │    │  internet or your laptop     │ │
│  └──────────────┘    └──────────────────────────────┘ │
│                                                       │
│  NOTHING LEAVES unless you say so.                    │
└──────────────────────────────────────────────────────┘
```

**What it does today:**
- Knows every device in your home (9 devices, 5 rooms)
- Runs security audits (finds default passwords, bad VLAN placement)
- Has 11 automation rules (wake → open blinds, sleep → arm cameras, etc.)
- Has 4 scenes (Movie Mode, Focus Mode, Away, Goodnight)
- Tracks Flipper Zero capabilities for security testing
- Encrypts all credentials in the Vault

**What it CAN'T do yet:**
- Actually talk to your devices (API calls are stubs — logged but not executed)
- Scan your network for new/rogue devices (stub — returns empty)
- Send commands over USB to Flipper Zero

---

## Files You Own

| File | Lines | What It Does |
|------|-------|-------------|
| `guardian_one/homelink/gateway.py` | ~300 | **API gateway** — TLS enforcement, rate limiting, circuit breaker for all external calls |
| `guardian_one/homelink/vault.py` | ~250 | **Encrypted credential storage** — PBKDF2 + Fernet, rotation tracking |
| `guardian_one/homelink/registry.py` | ~600 | **Integration catalog** — 27 services with threat models (5 risks each) |
| `guardian_one/homelink/monitor.py` | ~200 | **Health monitoring** — risk scores, anomaly detection, weekly security brief |
| `guardian_one/homelink/devices.py` | ~500 | **Device inventory** — 9 devices, 5 rooms, 6 Flipper profiles, security audit |
| `guardian_one/homelink/automations.py` | ~400 | **Automation engine** — 11 rules, 4 scenes, trigger evaluation |
| `guardian_one/agents/device_agent.py` | ~450 | **Device orchestrator** — ties it all together, handles events from Chronos |
| `tests/test_homelink.py` | ~400 | 39 tests for Gateway, Vault, Registry, Monitor |
| `tests/test_devices.py` | 658 | 58 tests for devices, rooms, automations, agent |

---

## Your Device Inventory

| Device | What | Where | Protocols | Status |
|--------|------|-------|-----------|--------|
| **cam-01** | Security Camera | Front exterior | WiFi, LAN API | Placeholder — need to pick manufacturer |
| **motion-01** | Motion Detector | Living room | WiFi | Placeholder — pairs with cam-01 |
| **tv-samsung-main** | Samsung The Frame 65" QLED 4K (QN65LS03FADXZA) | Living room | WiFi, LAN API, BLE, IR | Tizen OS — ACR disabled, voice off, SmartThings hub off, telemetry blocked, IoT VLAN isolated |
| **plug-tplink-01** | TP-Link Smart Plug | Living room | WiFi, LAN API | Real — uses python-kasa (local only) |
| **light-hue-bridge** | Philips Hue Bridge | Bedroom | Zigbee, LAN API | Real — Hue Bridge on local HTTPS |
| **light-govee-01** | Govee Light Strip | Living room | WiFi, BLE, LAN UDP | Real — prefers local UDP control |
| **vehicle-01** | Connected Vehicle | Garage | OBD-II, Cloud API | Placeholder — GPS is PII |
| **blind-ryse-01** | Ryse SmartShade Motor | Living room | BLE, WiFi, Cloud | Real — SmartBridge local API |
| **flipper-zero** | Flipper Zero | Office | RF, NFC, IR, BLE, USB | Real — security testing tool |

## Your Rooms

| Room | Devices | Auto-Lights | Auto-Blinds |
|------|---------|-------------|-------------|
| **Living Room** | TV, Govee light, TP-Link plug, Ryse blind, motion detector | Yes | Yes |
| **Master Bedroom** | Hue Bridge (controls Zigbee bulbs) | Yes | Yes |
| **Office** | Flipper Zero | Yes | No |
| **Front Exterior** | Security camera | No | No |
| **Garage** | Vehicle | No | No |

## Your Automation Rules (11)

| When | What Happens | Priority |
|------|-------------|----------|
| **You wake up** | Blinds open, living room lights to 80% | 1-2 |
| **You go to sleep** | Blinds close, all lights off, cameras armed | 1-2 |
| **You leave home** | Blinds close, cameras armed, plugs off, lights off | 1 |
| **You arrive home** | Blinds open, lights to 70%, cameras disarmed | 1 |
| **Sunset** | Blinds close (privacy) | 3 |
| **Sunrise** | Blinds open (natural light) | 3 |
| **Motion detected** | Living room lights to 60% | 4 |
| **No motion for 15 min** | Dim lights to 20% | 5 |

## Your Scenes (4)

| Scene | What It Does |
|-------|-------------|
| **Movie Mode** | Blinds close, lights dim warm to 10%, TV on |
| **Focus Mode** | Office blinds open, lights 100% daylight, TV off |
| **Away Mode** | Everything off, blinds closed, cameras armed |
| **Goodnight** | Everything off, blinds closed, cameras armed, bedroom dim warm at 5% |

---

## Security Architecture (How Your Home Stays Safe)

### Network Isolation (VLAN)
```
┌─────────────────────┐     ┌─────────────────────┐
│  TRUSTED LAN         │     │  IoT VLAN            │
│  Your laptop, phone  │  ✕  │  Cameras, plugs,     │
│  Guardian One server │ ←──→│  lights, TV, blinds   │
│                      │     │  NO internet access   │
└─────────────────────┘     └─────────────────────┘
        │                           │
        │  Guardian One is the      │
        │  ONLY bridge between      │
        │  your trusted network     │
        │  and your IoT devices.    │
        └───────────────────────────┘
```

**Why this matters**: Your smart TV can't phone home to Samsung. Your camera
can't upload footage to some Chinese server. Your plugs can't be part of a
botnet. They only talk to Guardian One on YOUR network.

### Credential Security
- Every device password stored in the **Vault** (AES-encrypted)
- Passwords loaded **on-demand** (never sitting in memory)
- Rotation tracking (alerts when passwords are 90+ days old)
- No credentials ever appear in logs

### Threat Models (Built-In)
Every device integration has 5 documented risks with mitigations:

| Integration | Top Risk | Mitigation |
|-------------|---------|------------|
| TP-Link Kasa | XOR obfuscation (not real encryption) | Local-only mode, block cloud |
| Philips Hue | Bridge API key theft | Vault storage, LAN-only access |
| Govee | Cloud API data harvesting | Prefer local UDP, block cloud |
| Security Cameras | Default passwords | Audit flags CRITICAL, force change |
| Vehicle | GPS location = PII | OBD-II read-only, no remote access |
| Ryse Shades | BLE pairing intercept | Local SmartBridge only |
| Flipper Zero | Legal RF compliance | Authorized testing only, FCC limits |
| Smart TV | ACR data harvesting | ACR disabled, telemetry blocked at router |

### Security Audit (Auto-Runs)
The system checks for:
- Default passwords not changed → **CRITICAL**
- UPnP enabled → **HIGH**
- IoT device on trusted LAN → **HIGH** (should be on IoT VLAN)
- Camera depending on cloud → **HIGH**
- Unencrypted streams → **HIGH**
- Unknown firmware → **MEDIUM**

---

## What's Working vs What's Stubbed

### Fully Working
- Device registry (all CRUD, queries, room mapping)
- Automation engine (rules, scenes, trigger evaluation, execution history)
- Security audit logic (6 checks, risk scoring 1-5)
- Flipper Zero profile management
- H.O.M.E. L.I.N.K. Gateway (TLS, rate limiting, circuit breaker)
- Vault (encrypted storage, rotation tracking, health reports)
- Registry (27 integrations with threat models)
- Monitor (health snapshots, anomaly detection, weekly brief)
- Dashboard text rendering (full ASCII dashboard)
- 97 tests passing (39 homelink + 58 devices)

### Stubs (Need Real Implementation)

| Feature | Current State | What's Needed |
|---------|--------------|---------------|
| **Device API calls** | `_execute_actions()` logs but doesn't call real APIs | Implement python-kasa, phue, Govee LAN, Ryse SmartBridge, ONVIF drivers |
| **Network scanning** | `scan_network()` returns empty list | Implement ARP scan, mDNS, SSDP, ONVIF discovery, python-kasa discovery |
| **Flipper USB** | Profile data only, no serial communication | Implement USB serial protocol for IR/NFC/sub-GHz |
| **Firmware checking** | Data model exists, no actual version checking | Query device APIs for firmware versions |
| **VLAN enforcement** | Detects misconfiguration, can't fix it | Would need router API (pfSense, UniFi, etc.) |

---

## Development Tracks

### Track 1: Real Device Drivers (Priority — Makes It Actually Work)

Wire up `_execute_actions()` to real device APIs:

```python
# What exists (stub):
def _execute_actions(self, actions, source):
    for action in actions:
        self._action_log.append({...})  # just logs

# What's needed:
def _execute_actions(self, actions, source):
    for action in actions:
        if action.action_type in (ActionType.BLIND_OPEN, ActionType.BLIND_CLOSE):
            self._ryse_command(action)   # Ryse SmartBridge API
        elif action.action_type in (ActionType.LIGHT_ON, ActionType.LIGHT_OFF, ActionType.LIGHT_DIM):
            self._light_command(action)  # phue or Govee LAN
        elif action.action_type in (ActionType.DEVICE_ON, ActionType.DEVICE_OFF):
            self._plug_command(action)   # python-kasa
        elif action.action_type in (ActionType.CAMERA_ARM, ActionType.CAMERA_DISARM):
            self._camera_command(action) # ONVIF/RTSP
```

**Libraries to use:**
- `python-kasa` — TP-Link smart plugs/switches (async, local LAN)
- `phue` — Philips Hue Bridge (local HTTPS, Zigbee)
- `govee-api-launchdarkly` or raw UDP — Govee local control
- `onvif-zeep` — ONVIF camera discovery + control
- `pyserial` — Flipper Zero USB communication

### Track 2: Network Discovery (Find Devices Automatically)

```python
def scan_network(self):
    discovered = []
    # ARP scan: find all MAC addresses on local subnet
    # mDNS: find devices advertising services (.local)
    # SSDP/UPnP: find devices advertising via UPnP
    # python-kasa discover: find TP-Link devices
    # ONVIF probe: find cameras
    return discovered
```

Then `detect_unknown_devices()` already compares scan results vs registry
and flags anything unknown.

### Track 3: Router Integration (Network Security Control)

Connect to your router to actually enforce network rules:
- pfSense API or UniFi Controller API
- Create/verify IoT VLAN exists
- Block IoT → internet traffic
- Block IoT → trusted LAN traffic
- Allow Guardian One → IoT VLAN (one-way bridge)

### Track 4: Live Device Status

Poll devices periodically to update online/offline status:
- Ping devices on IoT VLAN
- Query python-kasa for plug state (on/off, energy usage)
- Query Hue Bridge for light state (on/off, brightness, color)
- Query cameras for stream status

### Track 5: Flipper Zero USB Integration

```python
# Serial protocol for Flipper Zero
import serial
flipper = serial.Serial('/dev/ttyACM0', 115200)
flipper.write(b'ir tx infrared/tv_main.ir\r\n')  # Send IR command
flipper.write(b'subghz tx ...\r\n')               # Send sub-GHz
```

### Track 6: Guardian AI + Voice Control

Use the AI engine to parse natural language commands:
```
"Hey Guardian, turn on movie mode"
"Lock up the house, I'm leaving"
"What devices are online?"
"Any security issues?"
```

This ties into the conversational router pattern from `HANDOFF_CFO_ROUTER.md`
but for the device agent instead of CFO.

---

## Key Method Signatures

### DeviceAgent (guardian_one/agents/device_agent.py)
```python
# Lifecycle
agent.initialize() -> None
agent.run() -> None
agent.report() -> AgentReport

# Event handlers (called by Chronos)
agent.handle_schedule_event(event: str) -> list[dict]   # "wake", "sleep", "leave", "arrive"
agent.handle_occupancy_event(state: str, room_id: str) -> list[dict]  # "detected", "cleared"
agent.handle_solar_event(event: str) -> list[dict]      # "sunrise", "sunset"
agent.activate_scene(scene_id: str) -> list[dict]       # "scene-movie", etc.

# Device management
agent.add_device(device: DeviceRecord) -> None
agent.remove_device(device_id: str) -> None
agent.get_device(device_id: str) -> DeviceRecord | None
agent.list_devices() -> list[DeviceRecord]

# Network
agent.scan_network() -> dict                  # STUB — needs implementation
agent.detect_unknown_devices() -> list[dict]  # compares scan vs registry

# Ecosystem queries
agent.hue_devices() -> list[DeviceRecord]
agent.govee_devices() -> list[DeviceRecord]
agent.tplink_devices() -> list[DeviceRecord]
agent.ryse_devices() -> list[DeviceRecord]
agent.cameras() -> list[DeviceRecord]
agent.blinds() -> list[DeviceRecord]
agent.security_devices() -> list[DeviceRecord]

# Reporting
agent.flipper_audit() -> dict
agent.dashboard_text() -> str
agent.action_history(limit=50) -> list[dict]
```

### DeviceRegistry (guardian_one/homelink/devices.py)
```python
registry.register(device: DeviceRecord) -> None
registry.get(device_id: str) -> DeviceRecord | None
registry.remove(device_id: str) -> bool
registry.all_devices() -> list[DeviceRecord]
registry.by_category(cat: DeviceCategory) -> list[DeviceRecord]
registry.by_segment(seg: NetworkSegment) -> list[DeviceRecord]
registry.by_protocol(proto: DeviceProtocol) -> list[DeviceRecord]
registry.by_status(status: DeviceStatus) -> list[DeviceRecord]
registry.update_status(device_id: str, status: DeviceStatus) -> None
registry.security_audit() -> dict   # issues[], risk_score 1-5

# Rooms
registry.add_room(room: Room) -> None
registry.get_room(room_id: str) -> Room | None
registry.all_rooms() -> list[Room]
registry.devices_in_room(room_id: str) -> list[DeviceRecord]

# Flipper
registry.add_flipper_profile(profile: FlipperProfile) -> None
registry.flipper_controllable_devices() -> list[dict]
```

### AutomationEngine (guardian_one/homelink/automations.py)
```python
engine.add_rule(rule: AutomationRule) -> None
engine.get_rule(rule_id: str) -> AutomationRule | None
engine.remove_rule(rule_id: str) -> bool
engine.enabled_rules() -> list[AutomationRule]
engine.evaluate_trigger(trigger_type: TriggerType, context: dict) -> list[AutomationAction]
engine.add_scene(scene: Scene) -> None
engine.activate_scene(scene_id: str) -> list[AutomationAction]
engine.summary() -> dict
```

### Gateway (guardian_one/homelink/gateway.py)
```python
gw.register_service(config: ServiceConfig) -> None
gw.request(service_name: str, path: str, method: str, headers: dict, body: bytes, agent: str) -> dict
gw.service_status(name: str) -> dict   # circuit state, success rate, latency
gw.all_services_status() -> list[dict]
```

### Vault (guardian_one/homelink/vault.py)
```python
vault.store(key_name: str, value: str, service: str, scope: str, rotation_days: int) -> None
vault.retrieve(key_name: str) -> str
vault.rotate(key_name: str, new_value: str) -> None
vault.delete(key_name: str) -> None
vault.health_report() -> dict  # total, rotation_due[], expired[]
```

### Monitor (guardian_one/homelink/monitor.py)
```python
monitor.all_health() -> list[ServiceHealthSnapshot]
monitor.detect_anomalies() -> list[AnomalyAlert]
monitor.weekly_brief() -> dict
monitor.weekly_brief_text() -> str
```

---

## CLI Commands

```bash
python main.py --devices              # Full H.O.M.E. L.I.N.K. dashboard
python main.py --device-audit         # Security audit (risk score + issues)
python main.py --rooms                # Room layout with device inventory
python main.py --scene movie          # Activate Movie Mode
python main.py --scene goodnight      # Activate Goodnight
python main.py --home-event wake      # Fire "wake" event (blinds open, lights on)
python main.py --home-event sleep     # Fire "sleep" event (everything off, cameras arm)
python main.py --home-event leave     # Fire "leave" event (lockdown)
python main.py --home-event arrive    # Fire "arrive" event (welcome home)
python main.py --flipper              # Flipper Zero profiles & capabilities
python main.py --homelink             # H.O.M.E. L.I.N.K. system status
python main.py --brief                # Weekly security brief
python main.py --connector-audit      # MCP attack surface audit
```

---

## Enums Quick Reference

```python
# Device types
DeviceCategory: SECURITY_CAMERA, MOTION_DETECTOR, SMART_PLUG, SMART_LIGHT,
    SMART_BLIND, SMART_TV, VEHICLE, SECURITY_TOOL, NETWORK_INFRA, MEDIA_PLAYER, SENSOR, OTHER

# How devices talk
DeviceProtocol: WIFI, ZIGBEE, Z_WAVE, BLUETOOTH, BLE, MATTER, LAN_API, CLOUD_API,
    RF_433, RF_868, RF_SUB_GHZ, NFC, IR, OBD2, MQTT, USB

# Network zones
NetworkSegment: IOT_VLAN, TRUSTED_LAN, GUEST, DMZ, NOT_NETWORKED

# Room types
RoomType: BEDROOM, LIVING_ROOM, KITCHEN, BATHROOM, OFFICE, HALLWAY, GARAGE, EXTERIOR, ENTRY, OTHER

# What triggers automations
TriggerType: SCHEDULE, OCCUPANCY, SUNRISE, SUNSET, DEVICE_STATE, MANUAL, SYSTEM_EVENT

# What automations do
ActionType: DEVICE_ON, DEVICE_OFF, BLIND_OPEN, BLIND_CLOSE, BLIND_POSITION,
    LIGHT_ON, LIGHT_OFF, LIGHT_DIM, LIGHT_COLOR, CAMERA_ARM, CAMERA_DISARM,
    NOTIFY, SCENE_ACTIVATE
```

---

## Config Section (guardian_config.yaml)

```yaml
device_agent:
  enabled: true
  schedule_interval_minutes: 15
  allowed_resources: [devices, network, smart_home, cameras]
  custom:
    iot_vlan_required: true
    block_iot_internet: true
    firmware_check_daily: true
    unknown_device_alert: true
    ecosystems:
      tplink_kasa:    { enabled: true, local_only: true }
      philips_hue:    { enabled: true, local_only: true, bridge_ip: "" }
      govee:          { enabled: true, prefer_lan: true }
      security_cameras: { enabled: true, local_nvr: true, rtsp_encryption: true }
      smart_tv:       { enabled: true, acr_disabled: true, telemetry_blocked: true }
      vehicle:        { enabled: true, obd2_readonly: true, remote_access: false }
      flipper_zero:   { enabled: true, authorized_testing_only: true }
```

---

## Test Commands

```bash
pytest tests/test_homelink.py -v    # 39 tests — Gateway, Vault, Registry, Monitor
pytest tests/test_devices.py -v     # 58 tests — Devices, Rooms, Automations, Agent
```

---

## Cross-Agent Integration Points

| Agent | Integration | How |
|-------|-------------|-----|
| **Chronos** → DeviceAgent | Schedule events | `device_agent.handle_schedule_event("wake")` |
| **Chronos** → DeviceAgent | Solar events | `device_agent.handle_solar_event("sunrise")` |
| **CFO** → DeviceAgent | Energy cost tracking | Smart plug power usage → CFO utility budget |
| **Gmail** → DeviceAgent | Security alerts | Camera motion → email notification |
| **Archivist** → DeviceAgent | Camera footage | Local NVR storage management |
| **WebArchitect** → DeviceAgent | Dashboard | Home status on jtmdai.com |

---

## Dangerous MCP Connectors (Flagged for Disconnect)

The registry tracks 4 high-risk Claude Code connectors that should be
disconnected when not actively in use:

| Connector | Risk | Why |
|-----------|------|-----|
| Desktop Commander | **CRITICAL** | Full shell execution access |
| Filesystem MCP | **HIGH** | Bypasses Vault encryption |
| AWS MCP | **HIGH** | Credential exposure risk |
| Windows MCP | **HIGH** | PowerShell + registry modification |
