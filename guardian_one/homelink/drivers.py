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
    """Controls Philips Hue lights via the Hue Bridge local API.

    The Hue Bridge is the gateway to all Hue bulbs (Zigbee mesh).
    phue library sends HTTP PUT/GET to the bridge's REST API.

    Usage:
        driver = HueDriver(bridge_ip="192.168.1.10", api_key="abc123")
        result = driver.turn_on(light_id=1, brightness=200)
        result = driver.set_color(light_id=1, hue=10000, sat=254)
    """

    def __init__(self, bridge_ip: str, api_key: str = "") -> None:
        self._bridge_ip = bridge_ip
        self._api_key = api_key
        self._bridge = None

    def _get_bridge(self):
        """Lazily initialize the phue Bridge object."""
        if self._bridge is not None:
            return self._bridge
        from phue import Bridge
        # phue stores/reads API key from ~/.python_hue by default.
        # If we have a key from Vault, set it directly.
        b = Bridge(self._bridge_ip)
        if self._api_key:
            b.username = self._api_key
        self._bridge = b
        return b

    def turn_on(
        self,
        light_id: int | str | None = None,
        group_id: int | None = None,
        brightness: int = 254,
    ) -> dict[str, Any]:
        """Turn on a light or group.

        Args:
            light_id: Individual light ID or name. None if using group.
            group_id: Group/room ID. None if using individual light.
            brightness: 1-254 (Hue scale).
        """
        try:
            b = self._get_bridge()
            cmd = {"on": True, "bri": max(1, min(254, brightness))}
            if group_id is not None:
                b.set_group(group_id, cmd)
                return _ok("light_on", target=f"group:{group_id}",
                           brightness=brightness)
            elif light_id is not None:
                b.set_light(light_id, cmd)
                return _ok("light_on", target=f"light:{light_id}",
                           brightness=brightness)
            else:
                return _fail("light_on", "No light_id or group_id specified")
        except ImportError:
            return _fail("light_on",
                         "phue not installed (pip install phue)")
        except Exception as exc:
            return _fail("light_on", str(exc))

    def turn_off(
        self,
        light_id: int | str | None = None,
        group_id: int | None = None,
    ) -> dict[str, Any]:
        try:
            b = self._get_bridge()
            cmd = {"on": False}
            if group_id is not None:
                b.set_group(group_id, cmd)
                return _ok("light_off", target=f"group:{group_id}")
            elif light_id is not None:
                b.set_light(light_id, cmd)
                return _ok("light_off", target=f"light:{light_id}")
            else:
                return _fail("light_off", "No light_id or group_id specified")
        except ImportError:
            return _fail("light_off",
                         "phue not installed (pip install phue)")
        except Exception as exc:
            return _fail("light_off", str(exc))

    def set_brightness(
        self,
        brightness_pct: int,
        light_id: int | str | None = None,
        group_id: int | None = None,
    ) -> dict[str, Any]:
        """Set brightness as a percentage (0-100) → Hue scale (1-254)."""
        try:
            b = self._get_bridge()
            bri = max(1, int(brightness_pct / 100 * 254))
            cmd = {"on": True, "bri": bri}
            if group_id is not None:
                b.set_group(group_id, cmd)
                target = f"group:{group_id}"
            elif light_id is not None:
                b.set_light(light_id, cmd)
                target = f"light:{light_id}"
            else:
                return _fail("light_dim", "No light_id or group_id specified")
            return _ok("light_dim", target=target,
                       brightness_pct=brightness_pct, bri_hue=bri)
        except ImportError:
            return _fail("light_dim",
                         "phue not installed (pip install phue)")
        except Exception as exc:
            return _fail("light_dim", str(exc))

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
        try:
            b = self._get_bridge()

            presets = {
                "warm": {"ct": 400},           # 2500K warm white
                "daylight": {"ct": 153},        # 6500K daylight
                "red": {"hue": 0, "sat": 254},
                "green": {"hue": 21845, "sat": 254},
                "blue": {"hue": 43690, "sat": 254},
            }

            if color_name and color_name.lower() in presets:
                cmd = {"on": True, **presets[color_name.lower()]}
            elif hue is not None:
                cmd = {"on": True, "hue": hue, "sat": sat}
            else:
                return _fail("light_color",
                             "No color specified (hue or color_name)")

            if group_id is not None:
                b.set_group(group_id, cmd)
                target = f"group:{group_id}"
            elif light_id is not None:
                b.set_light(light_id, cmd)
                target = f"light:{light_id}"
            else:
                return _fail("light_color",
                             "No light_id or group_id specified")
            return _ok("light_color", target=target, color=color_name or hue)
        except ImportError:
            return _fail("light_color",
                         "phue not installed (pip install phue)")
        except Exception as exc:
            return _fail("light_color", str(exc))

    def get_lights(self) -> dict[str, Any]:
        """List all lights on the bridge."""
        try:
            b = self._get_bridge()
            lights = b.get_light_objects("id")
            info = {
                lid: {"name": l.name, "on": l.on, "brightness": l.brightness}
                for lid, l in lights.items()
            }
            return _ok("get_lights", lights=info)
        except ImportError:
            return _fail("get_lights",
                         "phue not installed (pip install phue)")
        except Exception as exc:
            return _fail("get_lights", str(exc))

    def get_groups(self) -> dict[str, Any]:
        """List all groups/rooms on the bridge."""
        try:
            b = self._get_bridge()
            groups = b.get_group()
            return _ok("get_groups", groups=groups)
        except ImportError:
            return _fail("get_groups",
                         "phue not installed (pip install phue)")
        except Exception as exc:
            return _fail("get_groups", str(exc))


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

    def get_hue_driver(self, bridge_ip: str) -> HueDriver:
        api_key = self._vault_retrieve("HUE_BRIDGE_API_KEY") or ""
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
