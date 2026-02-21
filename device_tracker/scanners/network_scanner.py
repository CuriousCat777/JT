"""
Network Device Scanner

Detects devices on the local network using ARP tables and network interfaces.
"""

import subprocess
import re
import socket


def scan_network_devices() -> list[dict]:
    """Scan for devices on the local network."""
    devices = []

    # Get local network interfaces
    devices.extend(_scan_interfaces())

    # Get ARP table entries (other devices on the network)
    devices.extend(_scan_arp_table())

    return devices


def _scan_interfaces() -> list[dict]:
    """Detect local network interfaces."""
    devices = []
    try:
        result = subprocess.run(
            ["ip", "-o", "link", "show"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return devices

        for line in result.stdout.strip().splitlines():
            match = re.match(r"\d+:\s+(\S+?)(?:@\S+)?:\s+<(.+?)>.*link/(\S+)\s+([0-9a-f:]+)", line)
            if not match:
                continue
            iface, flags, link_type, mac = match.groups()
            if iface == "lo" or mac == "00:00:00:00:00:00":
                continue

            ip_addr = _get_interface_ip(iface)
            devices.append({
                "name": f"Network Interface: {iface}",
                "device_type": _guess_network_type(iface, link_type),
                "connection_type": link_type.upper() if link_type != "ether" else "Ethernet",
                "mac_address": mac,
                "ip_address": ip_addr,
                "model": iface,
            })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return devices


def _get_interface_ip(iface: str) -> str:
    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", iface], capture_output=True, text=True, timeout=5
        )
        match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", result.stdout)
        return match.group(1) if match else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _scan_arp_table() -> list[dict]:
    """Read ARP table to find other devices on the network."""
    devices = []
    try:
        result = subprocess.run(
            ["ip", "neigh", "show"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return devices

        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) < 5:
                continue
            ip = parts[0]
            mac_idx = None
            for i, p in enumerate(parts):
                if re.match(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", p, re.IGNORECASE):
                    mac_idx = i
                    break
            if mac_idx is None:
                continue
            mac = parts[mac_idx]
            state = parts[-1] if parts[-1] in ("REACHABLE", "STALE", "DELAY", "PROBE", "FAILED") else ""
            if state == "FAILED":
                continue

            hostname = _resolve_hostname(ip)
            name = hostname if hostname else f"Network Device ({ip})"
            devices.append({
                "name": name,
                "device_type": "network_device",
                "connection_type": "Network",
                "mac_address": mac,
                "ip_address": ip,
                "model": hostname or ip,
            })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return devices


def _resolve_hostname(ip: str) -> str:
    try:
        hostname = socket.gethostbyaddr(ip)[0]
        return hostname
    except (socket.herror, socket.gaierror, OSError):
        return ""


def _guess_network_type(iface: str, link_type: str) -> str:
    iface_lower = iface.lower()
    if iface_lower.startswith("wl") or "wifi" in iface_lower:
        return "wifi_adapter"
    if iface_lower.startswith("eth") or iface_lower.startswith("en"):
        return "ethernet_adapter"
    if iface_lower.startswith("docker") or iface_lower.startswith("br-"):
        return "virtual_adapter"
    if iface_lower.startswith("veth"):
        return "virtual_adapter"
    if "bluetooth" in iface_lower or iface_lower.startswith("bt"):
        return "bluetooth_adapter"
    return "network_adapter"
