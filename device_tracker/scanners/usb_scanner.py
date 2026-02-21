"""
USB Device Scanner

Detects USB devices connected to the system using /sys/bus/usb and lsusb.
"""

import subprocess
import re
from pathlib import Path


def scan_usb_devices() -> list[dict]:
    """Scan for connected USB devices."""
    devices = []

    # Try lsusb first (most reliable)
    try:
        result = subprocess.run(
            ["lsusb"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            devices = _parse_lsusb(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: read /sys/bus/usb/devices
    if not devices:
        devices = _scan_sysfs()

    return devices


def _parse_lsusb(output: str) -> list[dict]:
    devices = []
    for line in output.strip().splitlines():
        match = re.match(
            r"Bus (\d+) Device (\d+): ID ([0-9a-f:]+)\s+(.*)", line, re.IGNORECASE
        )
        if match:
            bus, dev_num, vid_pid, description = match.groups()
            # Skip root hubs
            if "root hub" in description.lower():
                continue
            vendor, product = (vid_pid.split(":") + [""])[:2]
            devices.append({
                "name": description.strip() or f"USB Device {vid_pid}",
                "device_type": _guess_usb_type(description),
                "connection_type": "USB",
                "serial_number": f"USB-{bus}-{dev_num}-{vid_pid}",
                "manufacturer": _extract_manufacturer(description),
                "model": description.strip(),
                "raw_id": vid_pid,
            })
    return devices


def _scan_sysfs() -> list[dict]:
    devices = []
    usb_path = Path("/sys/bus/usb/devices")
    if not usb_path.exists():
        return devices

    for dev_dir in usb_path.iterdir():
        if not dev_dir.is_dir():
            continue
        product_file = dev_dir / "product"
        manufacturer_file = dev_dir / "manufacturer"
        serial_file = dev_dir / "serial"
        if not product_file.exists():
            continue

        product = product_file.read_text().strip()
        manufacturer = manufacturer_file.read_text().strip() if manufacturer_file.exists() else ""
        serial = serial_file.read_text().strip() if serial_file.exists() else dev_dir.name

        name = f"{manufacturer} {product}".strip() if manufacturer else product
        devices.append({
            "name": name,
            "device_type": _guess_usb_type(name),
            "connection_type": "USB",
            "serial_number": serial,
            "manufacturer": manufacturer,
            "model": product,
        })
    return devices


def _guess_usb_type(description: str) -> str:
    desc = description.lower()
    type_keywords = {
        "keyboard": "keyboard",
        "mouse": "mouse",
        "storage": "storage",
        "mass storage": "storage",
        "flash": "storage",
        "thumb": "storage",
        "camera": "camera",
        "webcam": "camera",
        "audio": "audio",
        "headset": "audio",
        "speaker": "audio",
        "microphone": "audio",
        "printer": "printer",
        "scanner": "scanner",
        "hub": "usb_hub",
        "bluetooth": "bluetooth_adapter",
        "wifi": "network_adapter",
        "wireless": "network_adapter",
        "ethernet": "network_adapter",
        "gamepad": "gamepad",
        "controller": "gamepad",
        "phone": "phone",
        "tablet": "tablet",
        "monitor": "display",
        "display": "display",
    }
    for keyword, dev_type in type_keywords.items():
        if keyword in desc:
            return dev_type
    return "usb_device"


def _extract_manufacturer(description: str) -> str:
    known_brands = [
        "Logitech", "Corsair", "Razer", "SteelSeries", "Microsoft", "Apple",
        "Samsung", "SanDisk", "Kingston", "Seagate", "Western Digital", "WD",
        "HP", "Dell", "Lenovo", "ASUS", "Acer", "Sony", "LG", "Anker",
        "Belkin", "TP-Link", "Netgear", "Intel", "AMD", "NVIDIA", "Creative",
        "HyperX", "Elgato", "Blue", "Jabra", "Plantronics", "Bose",
    ]
    for brand in known_brands:
        if brand.lower() in description.lower():
            return brand
    return ""
