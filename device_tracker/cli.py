"""
Device Tracker CLI

Command-line interface for managing your device inventory.

Usage:
    python -m device_tracker scan              Full scan of all connected hardware
    python -m device_tracker scan usb          Scan USB devices only
    python -m device_tracker scan network      Scan network devices only
    python -m device_tracker scan bluetooth    Scan Bluetooth devices only
    python -m device_tracker list              List all tracked devices
    python -m device_tracker list --connected  List only connected devices
    python -m device_tracker list --type usb   Filter by device type
    python -m device_tracker show <id>         Show details for a specific device
    python -m device_tracker add               Manually add a device
    python -m device_tracker edit <id>         Edit device details
    python -m device_tracker assign <id>       Set assignment/location/use for a device
    python -m device_tracker condition <id>    Update device condition
    python -m device_tracker remove <id>       Remove a device from inventory
    python -m device_tracker history <id>      Show activity history for a device
    python -m device_tracker underused         Show devices that haven't been seen recently
    python -m device_tracker dashboard         Show full inventory dashboard
"""

import argparse
import sys
from datetime import datetime

from device_tracker.agent import DeviceAgent
from device_tracker.models import (
    init_db, get_device, list_devices, update_device, delete_device,
    add_device, get_device_history, get_underused_devices, get_device_stats,
    log_event,
)


def main():
    init_db()
    parser = argparse.ArgumentParser(
        prog="device_tracker",
        description="Track, index, and manage all your devices and gadgets.",
    )
    sub = parser.add_subparsers(dest="command")

    # scan
    scan_p = sub.add_parser("scan", help="Scan for connected hardware")
    scan_p.add_argument("scan_type", nargs="?", default="all",
                        choices=["all", "usb", "network", "bluetooth"])

    # list
    list_p = sub.add_parser("list", help="List tracked devices")
    list_p.add_argument("--connected", action="store_true", help="Only connected devices")
    list_p.add_argument("--type", dest="filter_type", default="", help="Filter by device type")

    # show
    show_p = sub.add_parser("show", help="Show device details")
    show_p.add_argument("device_id", type=int)

    # add
    add_p = sub.add_parser("add", help="Manually add a device")
    add_p.add_argument("name", help="Device name")
    add_p.add_argument("--type", dest="device_type", default="unknown")
    add_p.add_argument("--manufacturer", default="")
    add_p.add_argument("--model", default="")
    add_p.add_argument("--serial", default="")
    add_p.add_argument("--location", default="")
    add_p.add_argument("--assigned-to", default="")
    add_p.add_argument("--use", dest="current_use", default="")
    add_p.add_argument("--condition", default="good",
                        choices=["new", "good", "fair", "poor", "broken"])
    add_p.add_argument("--notes", default="")

    # edit
    edit_p = sub.add_parser("edit", help="Edit device fields")
    edit_p.add_argument("device_id", type=int)
    edit_p.add_argument("--name", default=None)
    edit_p.add_argument("--type", dest="device_type", default=None)
    edit_p.add_argument("--manufacturer", default=None)
    edit_p.add_argument("--model", default=None)
    edit_p.add_argument("--location", default=None)
    edit_p.add_argument("--notes", default=None)

    # assign
    assign_p = sub.add_parser("assign", help="Assign a device to a person/purpose/location")
    assign_p.add_argument("device_id", type=int)
    assign_p.add_argument("--to", dest="assigned_to", default=None, help="Who it's assigned to")
    assign_p.add_argument("--use", dest="current_use", default=None, help="What it's used for")
    assign_p.add_argument("--location", default=None, help="Where it is")

    # condition
    cond_p = sub.add_parser("condition", help="Update device condition")
    cond_p.add_argument("device_id", type=int)
    cond_p.add_argument("status", choices=["new", "good", "fair", "poor", "broken"])

    # remove
    rm_p = sub.add_parser("remove", help="Remove a device from inventory")
    rm_p.add_argument("device_id", type=int)

    # history
    hist_p = sub.add_parser("history", help="Show device event history")
    hist_p.add_argument("device_id", type=int)
    hist_p.add_argument("--limit", type=int, default=20)

    # underused
    under_p = sub.add_parser("underused", help="Show underused devices")
    under_p.add_argument("--days", type=int, default=30, help="Days since last seen")

    # dashboard
    sub.add_parser("dashboard", help="Full inventory dashboard")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "scan": cmd_scan,
        "list": cmd_list,
        "show": cmd_show,
        "add": cmd_add,
        "edit": cmd_edit,
        "assign": cmd_assign,
        "condition": cmd_condition,
        "remove": cmd_remove,
        "history": cmd_history,
        "underused": cmd_underused,
        "dashboard": cmd_dashboard,
    }
    commands[args.command](args)


# --- Command Implementations ---

def cmd_scan(args):
    agent = DeviceAgent()
    print(f"Scanning {'all' if args.scan_type == 'all' else args.scan_type} devices...\n")

    if args.scan_type == "all":
        results = agent.full_scan()
        for stype in ["usb", "network", "bluetooth"]:
            items = results.get(stype, [])
            errors = [i for i in items if isinstance(i, dict) and "error" in i]
            valid = [i for i in items if isinstance(i, dict) and "error" not in i]
            print(f"  {stype.upper():12s}  {len(valid)} device(s) found", end="")
            if errors:
                print(f"  (scanner error: {errors[0]['error']})", end="")
            print()
    else:
        scanner_map = {"usb": agent.scan_usb, "network": agent.scan_network, "bluetooth": agent.scan_bluetooth}
        raw = scanner_map[args.scan_type]()
        print(f"  Found {len(raw)} {args.scan_type} device(s)")

    new_devices = results.get("new", []) if args.scan_type == "all" else []
    if new_devices:
        print(f"\n  New devices discovered:")
        for name in new_devices:
            print(f"    + {name}")

    print(f"\nDone. Run 'python -m device_tracker list' to see all tracked devices.")


def cmd_list(args):
    devices = list_devices(filter_type=args.filter_type, connected_only=args.connected)
    if not devices:
        print("No devices found. Run 'python -m device_tracker scan' to discover hardware.")
        return

    print(f"\n{'ID':>4}  {'Status':8}  {'Type':18}  {'Condition':10}  {'Name'}")
    print(f"{'─'*4}  {'─'*8}  {'─'*18}  {'─'*10}  {'─'*30}")

    for d in devices:
        status = "ONLINE" if d["is_connected"] else "offline"
        print(f"{d['id']:>4}  {status:8}  {d['device_type']:18}  {d['condition']:10}  {d['name']}")

    print(f"\n  Total: {len(devices)} device(s)")
    if not args.connected:
        connected = sum(1 for d in devices if d["is_connected"])
        print(f"  Connected: {connected}  |  Disconnected: {len(devices) - connected}")


def cmd_show(args):
    dev = get_device(args.device_id)
    if not dev:
        print(f"Device #{args.device_id} not found.")
        return

    status = "ONLINE" if dev["is_connected"] else "OFFLINE"
    print(f"\n  Device #{dev['id']}: {dev['name']}  [{status}]")
    print(f"  {'─'*50}")
    fields = [
        ("Type", "device_type"), ("Manufacturer", "manufacturer"), ("Model", "model"),
        ("Serial #", "serial_number"), ("MAC Address", "mac_address"),
        ("IP Address", "ip_address"), ("Connection", "connection_type"),
        ("Condition", "condition"), ("Location", "location"),
        ("Assigned To", "assigned_to"), ("Current Use", "current_use"),
        ("Notes", "notes"), ("First Seen", "first_seen"), ("Last Seen", "last_seen"),
    ]
    for label, key in fields:
        val = dev.get(key, "")
        if val:
            print(f"  {label:14s}  {val}")
    print()


def cmd_add(args):
    device_id = add_device(
        name=args.name,
        device_type=args.device_type,
        manufacturer=args.manufacturer,
        model=args.model,
        serial_number=args.serial,
        location=args.location,
        assigned_to=args.assigned_to,
        current_use=args.current_use,
        condition=args.condition,
        notes=args.notes,
    )
    print(f"Added device #{device_id}: {args.name}")


def cmd_edit(args):
    dev = get_device(args.device_id)
    if not dev:
        print(f"Device #{args.device_id} not found.")
        return

    updates = {}
    for field in ["name", "device_type", "manufacturer", "model", "location", "notes"]:
        val = getattr(args, field, None)
        if val is not None:
            updates[field] = val

    if not updates:
        print("No fields to update. Use --name, --type, --manufacturer, --model, --location, or --notes.")
        return

    update_device(args.device_id, **updates)
    log_event(args.device_id, "edited", f"Updated: {', '.join(updates.keys())}")
    print(f"Updated device #{args.device_id}: {dev['name']}")


def cmd_assign(args):
    dev = get_device(args.device_id)
    if not dev:
        print(f"Device #{args.device_id} not found.")
        return

    updates = {}
    if args.assigned_to is not None:
        updates["assigned_to"] = args.assigned_to
    if args.current_use is not None:
        updates["current_use"] = args.current_use
    if args.location is not None:
        updates["location"] = args.location

    if not updates:
        print("Specify at least one: --to, --use, or --location")
        return

    update_device(args.device_id, **updates)
    log_event(args.device_id, "assigned", f"Assignment updated: {updates}")
    print(f"Updated assignment for #{args.device_id}: {dev['name']}")
    for k, v in updates.items():
        print(f"  {k}: {v}")


def cmd_condition(args):
    dev = get_device(args.device_id)
    if not dev:
        print(f"Device #{args.device_id} not found.")
        return

    old = dev["condition"]
    update_device(args.device_id, condition=args.status)
    log_event(args.device_id, "condition_changed", f"{old} -> {args.status}")
    print(f"Device #{args.device_id} condition: {old} -> {args.status}")


def cmd_remove(args):
    dev = get_device(args.device_id)
    if not dev:
        print(f"Device #{args.device_id} not found.")
        return

    confirm = input(f"Remove '{dev['name']}' (#{args.device_id})? [y/N] ").strip().lower()
    if confirm == "y":
        delete_device(args.device_id)
        print(f"Removed device #{args.device_id}: {dev['name']}")
    else:
        print("Cancelled.")


def cmd_history(args):
    dev = get_device(args.device_id)
    if not dev:
        print(f"Device #{args.device_id} not found.")
        return

    events = get_device_history(args.device_id, limit=args.limit)
    print(f"\n  History for #{args.device_id}: {dev['name']}")
    print(f"  {'─'*50}")
    if not events:
        print("  No events recorded.")
        return

    for e in events:
        ts = e["timestamp"][:19].replace("T", " ")
        print(f"  {ts}  [{e['event']:18}]  {e['details']}")
    print()


def cmd_underused(args):
    devices = get_underused_devices(days_threshold=args.days)
    if not devices:
        print(f"No underused devices (all seen within the last {args.days} days).")
        return

    print(f"\n  Devices not seen in {args.days}+ days:")
    print(f"  {'─'*60}")
    print(f"  {'ID':>4}  {'Type':18}  {'Last Seen':20}  {'Name'}")
    for d in devices:
        ls = d["last_seen"][:19].replace("T", " ")
        print(f"  {d['id']:>4}  {d['device_type']:18}  {ls:20}  {d['name']}")

    print(f"\n  Total underused: {len(devices)}")
    print(f"  Tip: Use 'assign <id> --use ...' to repurpose these devices.")


def cmd_dashboard(args):
    stats = get_device_stats()
    devices = list_devices()
    underused = get_underused_devices(days_threshold=30)

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║            DEVICE INVENTORY DASHBOARD            ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()
    print(f"  Total Devices:  {stats['total_devices']}")
    print(f"  Connected Now:  {stats['connected_now']}")
    print(f"  Disconnected:   {stats['disconnected']}")
    print(f"  Underused:      {len(underused)}")
    print()

    if stats["by_type"]:
        print("  BY TYPE:")
        for t, cnt in stats["by_type"].items():
            bar = "█" * cnt
            print(f"    {t:20s}  {cnt:3d}  {bar}")
        print()

    if stats["by_condition"]:
        print("  BY CONDITION:")
        for c, cnt in stats["by_condition"].items():
            print(f"    {c:10s}  {cnt}")
        print()

    # Show connected devices
    connected = [d for d in devices if d["is_connected"]]
    if connected:
        print("  CURRENTLY CONNECTED:")
        for d in connected:
            use = f" — {d['current_use']}" if d["current_use"] else ""
            loc = f" @ {d['location']}" if d["location"] else ""
            print(f"    #{d['id']:>3}  {d['name']}{use}{loc}")
        print()

    # Show underused devices
    if underused:
        print("  UNDERUSED (30+ days):")
        for d in underused[:5]:
            print(f"    #{d['id']:>3}  {d['name']}  (last seen: {d['last_seen'][:10]})")
        if len(underused) > 5:
            print(f"    ... and {len(underused) - 5} more")
        print()


if __name__ == "__main__":
    main()
