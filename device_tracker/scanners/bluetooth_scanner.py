"""
Bluetooth Device Scanner

Detects paired and nearby Bluetooth devices.
"""

import subprocess
import re


def scan_bluetooth_devices() -> list[dict]:
    """Scan for Bluetooth devices (paired and nearby)."""
    devices = []

    # Get paired devices
    devices.extend(_get_paired_devices())

    # Try a quick scan for nearby devices
    devices.extend(_scan_nearby())

    return devices


def _get_paired_devices() -> list[dict]:
    """List paired Bluetooth devices via bluetoothctl."""
    devices = []
    try:
        result = subprocess.run(
            ["bluetoothctl", "devices", "Paired"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            # Fallback: try without the "Paired" argument
            result = subprocess.run(
                ["bluetoothctl", "devices"],
                capture_output=True, text=True, timeout=10
            )

        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                match = re.match(r"Device\s+([0-9A-Fa-f:]+)\s+(.*)", line)
                if match:
                    mac, name = match.groups()
                    devices.append({
                        "name": name.strip(),
                        "device_type": _guess_bt_type(name),
                        "connection_type": "Bluetooth",
                        "mac_address": mac,
                        "model": name.strip(),
                    })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return devices


def _scan_nearby() -> list[dict]:
    """Quick scan for nearby discoverable Bluetooth devices."""
    devices = []
    try:
        result = subprocess.run(
            ["hcitool", "scan", "--flush"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines()[1:]:  # skip header
                match = re.match(r"\s+([0-9A-Fa-f:]+)\s+(.*)", line)
                if match:
                    mac, name = match.groups()
                    devices.append({
                        "name": name.strip() or f"BT Device ({mac})",
                        "device_type": _guess_bt_type(name),
                        "connection_type": "Bluetooth",
                        "mac_address": mac,
                        "model": name.strip(),
                    })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return devices


def _guess_bt_type(name: str) -> str:
    name_lower = name.lower()
    type_keywords = {
        "airpod": "earbuds",
        "earbud": "earbuds",
        "headphone": "headphones",
        "headset": "headset",
        "speaker": "speaker",
        "keyboard": "keyboard",
        "mouse": "mouse",
        "trackpad": "trackpad",
        "controller": "gamepad",
        "joystick": "gamepad",
        "watch": "smartwatch",
        "band": "fitness_tracker",
        "phone": "phone",
        "iphone": "phone",
        "galaxy": "phone",
        "pixel": "phone",
        "ipad": "tablet",
        "tablet": "tablet",
        "tv": "smart_tv",
        "printer": "printer",
        "car": "vehicle",
        "auto": "vehicle",
    }
    for keyword, dev_type in type_keywords.items():
        if keyword in name_lower:
            return dev_type
    return "bluetooth_device"
