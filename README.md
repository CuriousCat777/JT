# Device Tracker Agent

A personal hardware inventory agent that scans, indexes, and tracks all devices connected to your computer — so you always know what you have, where it is, and whether it's being used.

## Quick Start

```bash
# Scan all connected hardware (USB, Network, Bluetooth)
python -m device_tracker scan

# See everything you own
python -m device_tracker dashboard

# List all tracked devices
python -m device_tracker list
python -m device_tracker list --connected    # only online devices
python -m device_tracker list --type keyboard

# View details for a specific device
python -m device_tracker show 1
```

## Managing Devices

```bash
# Manually add a device (e.g. a gadget not connected right now)
python -m device_tracker add "Steam Deck" --type handheld --location "living room" --condition good

# Assign a device to a person/purpose/location
python -m device_tracker assign 3 --to "Home Office" --use "Daily coding" --location "Desk"

# Update condition
python -m device_tracker condition 5 fair

# See what's underused
python -m device_tracker underused
python -m device_tracker underused --days 14

# View a device's history
python -m device_tracker history 2

# Remove a device
python -m device_tracker remove 7
```

## What It Scans

| Scanner    | How It Works                                      |
|------------|---------------------------------------------------|
| **USB**    | `lsusb` + `/sys/bus/usb/devices` sysfs            |
| **Network**| `ip link`, `ip neigh` (ARP table), DNS resolution |
| **Bluetooth** | `bluetoothctl` paired devices + `hcitool` scan |

## Device Fields

Each device tracks:
- **Name, Type, Manufacturer, Model, Serial #**
- **MAC Address, IP Address, Connection Type**
- **Condition** — new / good / fair / poor / broken
- **Location** — where the device physically is
- **Assigned To** — who is using it
- **Current Use** — what it's being used for
- **Notes** — any extra info
- **First/Last Seen** — when the agent first and last detected it
- **Connected Status** — whether it's currently online

## Data Storage

All data is stored locally in `~/.device_tracker/devices.db` (SQLite). No cloud, no accounts — your inventory stays on your machine.
