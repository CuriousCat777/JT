"""Real device drivers for H.O.M.E. L.I.N.K. smart home control.

Drivers for:
- TP-Link Kasa/Tapo smart plugs (via python-kasa)
- Philips Hue lights (via phue)
- Govee LAN lights (raw UDP protocol)

Each driver follows a consistent pattern:
1. Initialize with connection info (IP, credentials from Vault)
2. Provide turn_on/turn_off/set_brightness/set_color as appropriate
3. Return a result dict with success/error status for audit logging
4. Handle connection failures gracefully (never raise into the caller)
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import struct
import time
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result helper
# ---------------------------------------------------------------------------

def _ok(action: str, **extra: Any) -> dict[str, Any]:
    return {"success": True, "action": action, "error": "", **extra}


def _fail(action: str, error: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "action": action, "error": error, **extra}


# ---------------------------------------------------------------------------
# Async helper — python-kasa is async, Guardian One is sync
# ---------------------------------------------------------------------------

def _run_async(coro):
    """Run an async coroutine from synchronous code."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside an event loop — create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=15)
    else:
        return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════
# TP-Link Kasa Driver (python-kasa)
# ═══════════════════════════════════════════════════════════════════════════

class KasaDriver:
    """Controls TP-Link Kasa/Tapo smart plugs over LAN.

    Uses python-kasa library which communicates via TP-Link's local
    encrypted protocol (no cloud dependency).

    Usage:
        driver = KasaDriver(ip="192.168.1.50")
        result = driver.turn_on()
        result = driver.turn_off()
    """

    def __init__(self, ip: str) -> None:
        self._ip = ip

    def turn_on(self) -> dict[str, Any]:
        try:
            from kasa import Discover
            async def _on():
                dev = await Discover.discover_single(self._ip, timeout=5)
                await dev.update()
                await dev.turn_on()
                await dev.update()
                return dev.is_on
            is_on = _run_async(_on())
            if is_on:
                return _ok("turn_on", device_ip=self._ip)
            return _fail("turn_on", "Device did not confirm on state",
                         device_ip=self._ip)
        except ImportError:
            return _fail("turn_on",
                         "python-kasa not installed (pip install python-kasa)",
                         device_ip=self._ip)
        except Exception as exc:
            return _fail("turn_on", str(exc), device_ip=self._ip)

    def turn_off(self) -> dict[str, Any]:
        try:
            from kasa import Discover
            async def _off():
                dev = await Discover.discover_single(self._ip, timeout=5)
                await dev.update()
                await dev.turn_off()
                await dev.update()
                return not dev.is_on
            is_off = _run_async(_off())
            if is_off:
                return _ok("turn_off", device_ip=self._ip)
            return _fail("turn_off", "Device did not confirm off state",
                         device_ip=self._ip)
        except ImportError:
            return _fail("turn_off",
                         "python-kasa not installed (pip install python-kasa)",
                         device_ip=self._ip)
        except Exception as exc:
            return _fail("turn_off", str(exc), device_ip=self._ip)

    def get_status(self) -> dict[str, Any]:
        try:
            from kasa import Discover
            async def _status():
                dev = await Discover.discover_single(self._ip, timeout=5)
                await dev.update()
                return {
                    "is_on": dev.is_on,
                    "alias": dev.alias,
                    "model": dev.model,
                    "rssi": getattr(dev, "rssi", None),
                }
            info = _run_async(_status())
            return _ok("get_status", device_ip=self._ip, **info)
        except ImportError:
            return _fail("get_status",
                         "python-kasa not installed (pip install python-kasa)",
                         device_ip=self._ip)
        except Exception as exc:
            return _fail("get_status", str(exc), device_ip=self._ip)


# ═══════════════════════════════════════════════════════════════════════════
# Philips Hue Driver (phue)
# ═══════════════════════════════════════════════════════════════════════════

class HueDriver:
    """Controls Philips Hue lights via the Hue Bridge local REST API.

    Zero external dependencies — uses stdlib urllib to hit the bridge
    directly over HTTPS/HTTP on the LAN.  No cloud, no phue library.

    Bridge at 192.168.1.147 (self-signed cert → verify=False).
    API docs: https://developers.meethue.com/develop/hue-api-v2/

    Usage:
        driver = HueDriver(bridge_ip="192.168.1.147", api_key="abc123")
        result = driver.turn_on(light_id="1", brightness=200)
        result = driver.get_lights()
    """

    def __init__(self, bridge_ip: str, api_key: str = "") -> None:
        self._bridge_ip = bridge_ip
        self._api_key = api_key

    @property
    def _base_url(self) -> str:
        return f"https://{self._bridge_ip}/api/{self._api_key}"

    def _request(
        self, method: str, path: str, body: dict | None = None,
    ) -> dict[str, Any]:
        """Send a request to the Hue Bridge local API."""
        import ssl
        import urllib.error
        import urllib.request

        if not self._api_key:
            return _fail(path, "No Hue API key — register with bridge first")

        url = f"{self._base_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, method=method, headers=headers)

        # Bridge uses self-signed cert — skip verification on LAN
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                result = json.loads(resp.read().decode())
                # Hue API returns a list for state changes
                if isinstance(result, list) and result:
                    if "error" in result[0]:
                        return _fail(path, result[0]["error"].get("description", str(result[0])))
                return _ok(method.lower(), path=path, data=result)
        except urllib.error.HTTPError as exc:
            return _fail(path, f"HTTP {exc.code}")
        except urllib.error.URLError as exc:
            return _fail(path, f"Connection failed: {exc.reason}")
        except Exception as exc:
            return _fail(path, str(exc))

    # ------------------------------------------------------------------
    # Light control
    # ------------------------------------------------------------------

    def turn_on(
        self,
        light_id: int | str | None = None,
        group_id: int | None = None,
        brightness: int = 254,
    ) -> dict[str, Any]:
        """Turn on a light or group.

        Args:
            light_id: Individual light ID. None if using group.
            group_id: Group/room ID. None if using individual light.
            brightness: 1-254 (Hue scale).
        """
        cmd = {"on": True, "bri": max(1, min(254, brightness))}
        if group_id is not None:
            return self._request("PUT", f"/groups/{group_id}/action", cmd)
        elif light_id is not None:
            return self._request("PUT", f"/lights/{light_id}/state", cmd)
        return _fail("light_on", "No light_id or group_id specified")

    def turn_off(
        self,
        light_id: int | str | None = None,
        group_id: int | None = None,
    ) -> dict[str, Any]:
        cmd = {"on": False}
        if group_id is not None:
            return self._request("PUT", f"/groups/{group_id}/action", cmd)
        elif light_id is not None:
            return self._request("PUT", f"/lights/{light_id}/state", cmd)
        return _fail("light_off", "No light_id or group_id specified")

    def set_brightness(
        self,
        brightness_pct: int,
        light_id: int | str | None = None,
        group_id: int | None = None,
    ) -> dict[str, Any]:
        """Set brightness as a percentage (0-100) → Hue scale (1-254)."""
        bri = max(1, int(brightness_pct / 100 * 254))
        cmd = {"on": True, "bri": bri}
        if group_id is not None:
            return self._request("PUT", f"/groups/{group_id}/action", cmd)
        elif light_id is not None:
            return self._request("PUT", f"/lights/{light_id}/state", cmd)
        return _fail("light_dim", "No light_id or group_id specified")

    def set_color(
        self,
        light_id: int | str | None = None,
        group_id: int | None = None,
        hue: int | None = None,
        sat: int = 254,
        color_name: str = "",
    ) -> dict[str, Any]:
        """Set light color.

        Args:
            hue: Hue value 0-65535 (red=0, green=~21845, blue=~43690).
            sat: Saturation 0-254.
            color_name: Named preset — 'warm', 'daylight', 'red', 'blue',
                        'green'. Overrides hue/sat if set.
        """
        presets = {
            "warm": {"on": True, "ct": 400},           # 2500K warm white
            "daylight": {"on": True, "ct": 153},        # 6500K daylight
            "red": {"on": True, "hue": 0, "sat": 254},
            "green": {"on": True, "hue": 21845, "sat": 254},
            "blue": {"on": True, "hue": 43690, "sat": 254},
        }

        if color_name and color_name.lower() in presets:
            cmd = presets[color_name.lower()]
        elif hue is not None:
            cmd = {"on": True, "hue": hue, "sat": sat}
        else:
            return _fail("light_color", "No color specified (hue or color_name)")

        if group_id is not None:
            return self._request("PUT", f"/groups/{group_id}/action", cmd)
        elif light_id is not None:
            return self._request("PUT", f"/lights/{light_id}/state", cmd)
        return _fail("light_color", "No light_id or group_id specified")

    # ------------------------------------------------------------------
    # Discovery / status
    # ------------------------------------------------------------------

    def get_lights(self) -> dict[str, Any]:
        """List all lights on the bridge."""
        return self._request("GET", "/lights")

    def get_light(self, light_id: int | str) -> dict[str, Any]:
        """Get state of a single light."""
        return self._request("GET", f"/lights/{light_id}")

    def get_groups(self) -> dict[str, Any]:
        """List all groups/rooms on the bridge."""
        return self._request("GET", "/groups")

    def get_config(self) -> dict[str, Any]:
        """Get bridge configuration (name, zigbee channel, sw version)."""
        return self._request("GET", "/config")

    def get_sensors(self) -> dict[str, Any]:
        """List all sensors (motion, daylight, switches)."""
        return self._request("GET", "/sensors")

    def get_scenes(self) -> dict[str, Any]:
        """List all scenes."""
        return self._request("GET", "/scenes")

    def activate_scene(self, group_id: int, scene_id: str) -> dict[str, Any]:
        """Activate a scene in a group."""
        return self._request("PUT", f"/groups/{group_id}/action", {"scene": scene_id})

    # ------------------------------------------------------------------
    # Registration (call after pressing bridge link button)
    # ------------------------------------------------------------------

    @staticmethod
    def register(bridge_ip: str, device_type: str = "guardian_one#homelink") -> dict[str, Any]:
        """Register a new API user on the bridge.

        Press the link button on the bridge FIRST, then call this within 30s.
        Returns the API username on success.
        """
        import ssl
        import urllib.error
        import urllib.request

        url = f"https://{bridge_ip}/api"
        data = json.dumps({"devicetype": device_type}).encode()
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                result = json.loads(resp.read().decode())
                if isinstance(result, list) and result:
                    if "success" in result[0]:
                        username = result[0]["success"]["username"]
                        return _ok("register", username=username, bridge_ip=bridge_ip)
                    elif "error" in result[0]:
                        desc = result[0]["error"].get("description", "")
                        return _fail("register", desc, bridge_ip=bridge_ip)
                return _fail("register", f"Unexpected response: {result}", bridge_ip=bridge_ip)
        except Exception as exc:
            return _fail("register", str(exc), bridge_ip=bridge_ip)


# ═══════════════════════════════════════════════════════════════════════════
# Govee LAN Driver (raw UDP protocol)
# ═══════════════════════════════════════════════════════════════════════════

class GoveeLanDriver:
    """Controls Govee lights via the local LAN UDP protocol.

    Protocol:
    - Discovery: send {"msg":{"cmd":"scan","data":{"account_topic":"reserve"}}}
      to 239.255.255.250:4001 (multicast)
    - Control: send JSON commands to device IP on port 4003 (unicast UDP)
    - Commands: turn, brightness, color, colorTem

    Supported on newer Govee models with LAN control enabled in the app.
    """

    MULTICAST_GROUP = "239.255.255.250"
    SCAN_PORT = 4001
    CONTROL_PORT = 4003

    def __init__(self, device_ip: str = "", device_sku: str = "") -> None:
        self._device_ip = device_ip
        self._device_sku = device_sku

    def _send_command(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Send a UDP command to the Govee device."""
        if not self._device_ip:
            return _fail(cmd.get("msg", {}).get("cmd", "unknown"),
                         "No device IP set — run discover() first")
        payload = json.dumps(cmd).encode("utf-8")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)
            sock.sendto(payload, (self._device_ip, self.CONTROL_PORT))
            try:
                data, _ = sock.recvfrom(4096)
                resp = json.loads(data.decode("utf-8"))
                return _ok(cmd["msg"]["cmd"], response=resp,
                           device_ip=self._device_ip)
            except socket.timeout:
                # Govee doesn't always ACK — treat send as success
                return _ok(cmd["msg"]["cmd"], device_ip=self._device_ip,
                           note="no_ack")
            finally:
                sock.close()
        except Exception as exc:
            return _fail(cmd.get("msg", {}).get("cmd", "unknown"),
                         str(exc), device_ip=self._device_ip)

    def turn_on(self) -> dict[str, Any]:
        return self._send_command({
            "msg": {
                "cmd": "turn",
                "data": {"value": 1},
            }
        })

    def turn_off(self) -> dict[str, Any]:
        return self._send_command({
            "msg": {
                "cmd": "turn",
                "data": {"value": 0},
            }
        })

    def set_brightness(self, brightness_pct: int) -> dict[str, Any]:
        """Set brightness 0-100."""
        return self._send_command({
            "msg": {
                "cmd": "brightness",
                "data": {"value": max(0, min(100, brightness_pct))},
            }
        })

    def set_color(
        self, r: int = 255, g: int = 255, b: int = 255
    ) -> dict[str, Any]:
        """Set RGB color (0-255 per channel)."""
        return self._send_command({
            "msg": {
                "cmd": "colorwc",
                "data": {
                    "color": {"r": r, "g": g, "b": b},
                    "colorTemInKelvin": 0,
                },
            }
        })

    def set_color_temperature(self, kelvin: int) -> dict[str, Any]:
        """Set white color temperature in Kelvin (2000-9000)."""
        return self._send_command({
            "msg": {
                "cmd": "colorwc",
                "data": {
                    "color": {"r": 0, "g": 0, "b": 0},
                    "colorTemInKelvin": max(2000, min(9000, kelvin)),
                },
            }
        })

    def discover(self, timeout: float = 3.0) -> list[dict[str, Any]]:
        """Discover Govee devices on the local network via multicast.

        Returns list of device info dicts with ip, sku, device name.
        """
        scan_msg = json.dumps({
            "msg": {
                "cmd": "scan",
                "data": {"account_topic": "reserve"},
            }
        }).encode("utf-8")

        devices: list[dict[str, Any]] = []
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                 socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(timeout)

            # Join multicast group
            mreq = struct.pack(
                "4sl",
                socket.inet_aton(self.MULTICAST_GROUP),
                socket.INADDR_ANY,
            )
            sock.setsockopt(socket.IPPROTO_IP,
                            socket.IP_ADD_MEMBERSHIP, mreq)
            sock.bind(("", self.SCAN_PORT))
            sock.sendto(scan_msg,
                        (self.MULTICAST_GROUP, self.SCAN_PORT))

            end_time = time.time() + timeout
            while time.time() < end_time:
                try:
                    data, addr = sock.recvfrom(4096)
                    resp = json.loads(data.decode("utf-8"))
                    if resp.get("msg", {}).get("cmd") == "scan":
                        dev_data = resp["msg"].get("data", {})
                        devices.append({
                            "ip": dev_data.get("ip", addr[0]),
                            "sku": dev_data.get("sku", ""),
                            "device": dev_data.get("device", ""),
                        })
                except socket.timeout:
                    break
                except json.JSONDecodeError:
                    continue
            sock.close()
        except Exception as exc:
            logger.warning("Govee LAN discovery failed: %s", exc)

        return devices


# ═══════════════════════════════════════════════════════════════════════════
# Govee Cloud API Driver (fallback when LAN IP not known)
# ═══════════════════════════════════════════════════════════════════════════

class GoveeCloudDriver:
    """Controls Govee lights via the Govee Developer Cloud API.

    This is a FALLBACK — the LAN driver (GoveeLanDriver) is preferred
    because it works locally without internet. Use this when:
    - Device IP is not yet discovered
    - Device doesn't support LAN control
    - LAN control hasn't been enabled in the Govee app yet

    Cloud API docs: https://developer-api.govee.com
    Rate limit: 100 requests per minute.
    API key stored in Vault as GOVEE_API_KEY.
    """

    BASE_URL = "https://developer-api.govee.com"

    def __init__(self, api_key: str, device_id: str = "", model: str = "") -> None:
        self._api_key = api_key
        self._device_id = device_id
        self._model = model

    def _request(self, method: str, path: str, body: dict | None = None) -> dict[str, Any]:
        """Make an authenticated request to the Govee Cloud API."""
        import urllib.request
        import urllib.error

        url = f"{self.BASE_URL}{path}"
        headers = {
            "Govee-API-Key": self._api_key,
            "Content-Type": "application/json",
        }
        data = json.dumps(body).encode("utf-8") if body else None

        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return _ok(path, response=result)
        except urllib.error.HTTPError as exc:
            return _fail(path, f"HTTP {exc.code}: {exc.reason}")
        except Exception as exc:
            return _fail(path, str(exc))

    def list_devices(self) -> dict[str, Any]:
        """List all devices on the Govee account."""
        return self._request("GET", "/v1/devices")

    def turn_on(self) -> dict[str, Any]:
        return self._control("turn", {"value": "on"})

    def turn_off(self) -> dict[str, Any]:
        return self._control("turn", {"value": "off"})

    def set_brightness(self, brightness_pct: int) -> dict[str, Any]:
        return self._control("brightness", {"value": max(0, min(100, brightness_pct))})

    def set_color(self, r: int = 255, g: int = 255, b: int = 255) -> dict[str, Any]:
        return self._control("color", {"value": {"r": r, "g": g, "b": b}})

    def set_color_temperature(self, kelvin: int) -> dict[str, Any]:
        return self._control("colorTem", {"value": max(2000, min(9000, kelvin))})

    def _control(self, cmd_name: str, cmd_value: dict) -> dict[str, Any]:
        if not self._device_id or not self._model:
            return _fail(cmd_name, "device_id and model required for cloud control")
        body = {
            "device": self._device_id,
            "model": self._model,
            "cmd": {
                "name": cmd_name,
                "value": cmd_value.get("value", cmd_value),
            },
        }
        return self._request("PUT", "/v1/devices/control", body)


# ═══════════════════════════════════════════════════════════════════════════
# LG WebOS TV driver — local SSAP volume control
# ═══════════════════════════════════════════════════════════════════════════

class LgWebOsDriver:
    """Control LG WebOS TV over local network via aiowebostv.

    Supports: volume up/down/set/mute, power off, input switching.
    The TV must accept the pairing request on first connection.
    """

    def __init__(self, ip: str, client_key: str = "") -> None:
        self._ip = ip
        self._client_key = client_key

    def _run(self, coro_factory):
        """Run an async WebOS command synchronously."""
        async def _do():
            try:
                from aiowebostv import WebOsTvClient
                client = WebOsTvClient(self._ip, self._client_key)
                await client.connect()
                result = await coro_factory(client)
                await client.disconnect()
                return _ok(result)
            except ImportError:
                return _fail("aiowebostv not installed")
            except Exception as e:
                return _fail(f"WebOS error: {e}")
        return asyncio.run(_do())

    def get_volume(self) -> dict[str, Any]:
        return self._run(lambda c: c.get_volume())

    def set_volume(self, level: int) -> dict[str, Any]:
        level = max(0, min(100, level))
        return self._run(lambda c: c.set_volume(level))

    def volume_up(self) -> dict[str, Any]:
        return self._run(lambda c: c.volume_up())

    def volume_down(self) -> dict[str, Any]:
        return self._run(lambda c: c.volume_down())

    def mute(self, muted: bool = True) -> dict[str, Any]:
        return self._run(lambda c: c.set_mute(muted))

    def turn_off(self) -> dict[str, Any]:
        return self._run(lambda c: c.power_off())


# ═══════════════════════════════════════════════════════════════════════════
# Driver factory — resolves device records to driver instances
# ═══════════════════════════════════════════════════════════════════════════

class DriverFactory:
    """Creates the right driver for a device based on its integration_name.

    Requires device IP addresses to be set in DeviceRecord and
    credentials to be available from Vault.
    """

    def __init__(self, vault_retrieve=None) -> None:
        """
        Args:
            vault_retrieve: Callable(key_name) -> str | None
                            Typically ``vault.retrieve``.
        """
        self._vault_retrieve = vault_retrieve or (lambda k: None)

    def get_kasa_driver(self, device_ip: str) -> KasaDriver:
        return KasaDriver(ip=device_ip)

    def get_hue_driver(self, bridge_ip: str = "192.168.1.147") -> HueDriver:
        api_key = (
            self._vault_retrieve("HUE_BRIDGE_API_KEY")
            or self._vault_retrieve("HUE_BRIDGE_USERNAME")
            or ""
        )
        return HueDriver(bridge_ip=bridge_ip, api_key=api_key)

    def get_govee_driver(self, device_ip: str) -> GoveeLanDriver:
        return GoveeLanDriver(device_ip=device_ip)

    def get_govee_cloud_driver(
        self, device_id: str = "", model: str = ""
    ) -> GoveeCloudDriver | None:
        """Get Govee cloud API driver (fallback). Returns None if no API key."""
        api_key = self._vault_retrieve("GOVEE_API_KEY")
        if not api_key:
            return None
        return GoveeCloudDriver(api_key=api_key, device_id=device_id, model=model)

    def get_lg_driver(self, tv_ip: str) -> LgWebOsDriver:
        client_key = self._vault_retrieve("LG_TV_CLIENT_KEY") or ""
        return LgWebOsDriver(ip=tv_ip, client_key=client_key)

    def for_device(self, device) -> KasaDriver | HueDriver | GoveeLanDriver | GoveeCloudDriver | LgWebOsDriver | None:
        """Return the appropriate driver for a DeviceRecord, or None.

        Priority for Govee: LAN driver (if IP known) > Cloud driver (if API key in Vault).
        """
        ip = device.ip_address
        if device.integration_name == "tplink_kasa":
            return self.get_kasa_driver(ip) if ip else None
        elif device.integration_name == "philips_hue":
            return self.get_hue_driver(ip) if ip else None
        elif device.integration_name == "govee":
            if ip:
                return self.get_govee_driver(ip)
            # Fallback: cloud API if Vault has the key
            return self.get_govee_cloud_driver(
                device_id=getattr(device, 'device_id', ''),
                model=getattr(device, 'model', ''),
            )
        elif device.category and device.category.value == "smart_tv":
            return self.get_lg_driver(ip) if ip else None
        return None
