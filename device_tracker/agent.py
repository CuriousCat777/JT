"""
Device Tracker Agent

The core agent that orchestrates scanning, indexing, and tracking all hardware.
"""

from device_tracker.models import (
    init_db, add_device, update_device, find_device, list_devices,
    log_event, log_scan, get_device_stats, get_underused_devices, now_iso,
)
from device_tracker.scanners.usb_scanner import scan_usb_devices
from device_tracker.scanners.network_scanner import scan_network_devices
from device_tracker.scanners.bluetooth_scanner import scan_bluetooth_devices


class DeviceAgent:
    """Agent that scans, indexes, and tracks all connected hardware."""

    def __init__(self):
        init_db()

    def full_scan(self) -> dict:
        """Run all scanners and update the device database."""
        results = {"usb": [], "network": [], "bluetooth": [], "new": [], "updated": []}

        # Mark all devices as disconnected before scanning
        for dev in list_devices():
            update_device(dev["id"], is_connected=0)

        # Run each scanner
        scanners = [
            ("usb", scan_usb_devices),
            ("network", scan_network_devices),
            ("bluetooth", scan_bluetooth_devices),
        ]

        total_found = 0
        total_new = 0

        for scan_type, scanner_fn in scanners:
            try:
                raw_devices = scanner_fn()
                results[scan_type] = raw_devices
                new_count = 0
                for raw in raw_devices:
                    was_new = self._upsert_device(raw, results)
                    if was_new:
                        new_count += 1
                total_found += len(raw_devices)
                total_new += new_count
                log_scan(scan_type, len(raw_devices), new_count)
            except Exception as e:
                results[scan_type] = [{"error": str(e)}]

        log_scan("full", total_found, total_new)
        return results

    def scan_usb(self) -> list[dict]:
        """Scan USB devices only."""
        results = {"new": [], "updated": []}
        raw = scan_usb_devices()
        for dev in raw:
            self._upsert_device(dev, results)
        log_scan("usb", len(raw), len(results["new"]))
        return raw

    def scan_network(self) -> list[dict]:
        """Scan network devices only."""
        results = {"new": [], "updated": []}
        raw = scan_network_devices()
        for dev in raw:
            self._upsert_device(dev, results)
        log_scan("network", len(raw), len(results["new"]))
        return raw

    def scan_bluetooth(self) -> list[dict]:
        """Scan Bluetooth devices only."""
        results = {"new": [], "updated": []}
        raw = scan_bluetooth_devices()
        for dev in raw:
            self._upsert_device(dev, results)
        log_scan("bluetooth", len(raw), len(results["new"]))
        return raw

    def _upsert_device(self, raw: dict, results: dict) -> bool:
        """Insert a new device or update an existing one. Returns True if new."""
        existing = None
        if raw.get("mac_address"):
            existing = find_device(mac_address=raw["mac_address"])
        if not existing and raw.get("serial_number"):
            existing = find_device(serial_number=raw["serial_number"])

        if existing:
            update_device(
                existing["id"],
                is_connected=1,
                last_seen=now_iso(),
                ip_address=raw.get("ip_address", existing.get("ip_address", "")),
            )
            log_event(existing["id"], "seen", f"Device detected during scan")
            results.setdefault("updated", []).append(existing["name"])
            return False
        else:
            device_id = add_device(
                name=raw.get("name", "Unknown Device"),
                device_type=raw.get("device_type", "unknown"),
                manufacturer=raw.get("manufacturer", ""),
                model=raw.get("model", ""),
                serial_number=raw.get("serial_number", ""),
                mac_address=raw.get("mac_address", ""),
                ip_address=raw.get("ip_address", ""),
                connection_type=raw.get("connection_type", ""),
                is_connected=1,
            )
            results.setdefault("new", []).append(raw.get("name", "Unknown"))
            return True

    def get_summary(self) -> dict:
        """Get a summary of the entire device inventory."""
        stats = get_device_stats()
        underused = get_underused_devices(days_threshold=30)
        all_devices = list_devices()

        return {
            "stats": stats,
            "underused_devices": [
                {"id": d["id"], "name": d["name"], "type": d["device_type"],
                 "last_seen": d["last_seen"], "assigned_to": d["assigned_to"]}
                for d in underused
            ],
            "all_devices": all_devices,
        }
