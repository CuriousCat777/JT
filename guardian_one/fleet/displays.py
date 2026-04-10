"""Display Topology — Monitor and TV layout management.

Maps Jeremy's physical display setup:
    1. Samsung 49" Ultrawide (CRG9/G9) — Primary workspace, split A|B
    2. Alienware 25" — Secondary monitor for A (ROG)
    3. LG NanoCell 65" — Living room / extended display
    4. Samsung Frame 65" — Living room / Mac Mini output or ambient art

Display zones allow Guardian One to:
- Route windows/apps to the correct physical screen
- Optimize wallpaper/ambient display for TVs
- Coordinate screen sharing between nodes
- Manage energy (turn off TVs when not needed)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DisplayType(Enum):
    MONITOR = "monitor"
    TV = "tv"
    LAPTOP_SCREEN = "laptop_screen"
    TABLET_SCREEN = "tablet_screen"


class DisplayConnection(Enum):
    HDMI = "hdmi"
    DISPLAYPORT = "displayport"
    USB_C_DP = "usb_c_dp"
    THUNDERBOLT = "thunderbolt"
    WIRELESS = "wireless"


class DisplayPosition(Enum):
    """Physical position relative to user seating position."""
    CENTER_LEFT = "center_left"
    CENTER_RIGHT = "center_right"
    LEFT = "left"
    RIGHT = "right"
    ABOVE = "above"
    WALL_LEFT = "wall_left"
    WALL_RIGHT = "wall_right"
    WALL_FRONT = "wall_front"


@dataclass
class DisplaySpec:
    """Physical display specification."""
    display_id: str
    name: str
    display_type: DisplayType
    manufacturer: str
    model: str

    # Physical specs
    size_inches: float
    resolution_width: int
    resolution_height: int
    refresh_rate_hz: int = 60
    hdr: bool = False
    panel_type: str = ""        # IPS, VA, OLED, QLED

    # Connection
    connection: DisplayConnection = DisplayConnection.HDMI
    connected_to_node: str = ""  # node_id of the machine driving this display

    # Layout
    position: DisplayPosition = DisplayPosition.CENTER_LEFT
    is_primary: bool = False
    split_between_nodes: bool = False  # True for ultrawide shared by A and B
    split_node_left: str = ""    # Node driving the left half
    split_node_right: str = ""   # Node driving the right half

    # Power
    supports_cec: bool = False   # HDMI-CEC for power control
    auto_off_minutes: int = 0    # 0 = manual only

    # Metadata
    notes: str = ""


class DisplayTopology:
    """Manages the full display layout for the fleet.

    Knows which displays exist, how they're connected, and which
    compute node drives each one.
    """

    def __init__(self) -> None:
        self._displays: dict[str, DisplaySpec] = {}

    def register(self, display: DisplaySpec) -> None:
        self._displays[display.display_id] = display

    def get(self, display_id: str) -> DisplaySpec | None:
        return self._displays.get(display_id)

    def all_displays(self) -> list[DisplaySpec]:
        return list(self._displays.values())

    def by_node(self, node_id: str) -> list[DisplaySpec]:
        """All displays connected to (or split with) a given node."""
        return [
            d for d in self._displays.values()
            if d.connected_to_node == node_id
            or d.split_node_left == node_id
            or d.split_node_right == node_id
        ]

    def by_type(self, display_type: DisplayType) -> list[DisplaySpec]:
        return [d for d in self._displays.values() if d.display_type == display_type]

    def monitors(self) -> list[DisplaySpec]:
        return self.by_type(DisplayType.MONITOR)

    def tvs(self) -> list[DisplaySpec]:
        return self.by_type(DisplayType.TV)

    def total_pixels(self) -> int:
        return sum(d.resolution_width * d.resolution_height for d in self._displays.values())

    def summary(self) -> dict[str, Any]:
        displays = self.all_displays()
        return {
            "total_displays": len(displays),
            "monitors": len(self.monitors()),
            "tvs": len(self.tvs()),
            "total_resolution": f"{self.total_pixels():,} pixels",
            "displays": [
                {
                    "id": d.display_id,
                    "name": d.name,
                    "size": f'{d.size_inches}"',
                    "resolution": f"{d.resolution_width}x{d.resolution_height}",
                    "refresh": f"{d.refresh_rate_hz}Hz",
                    "node": d.connected_to_node or f"{d.split_node_left}|{d.split_node_right}",
                    "position": d.position.value,
                }
                for d in displays
            ],
        }

    def layout_diagram(self) -> str:
        """ASCII art of the physical display layout."""
        return """
  JEREMY'S DISPLAY TOPOLOGY — OFFICE + LIVING ROOM
  ==================================================

  OFFICE DESK (seated position facing forward):
  ┌──────────────────────────────────────────────────────┐  ┌────────────────┐
  │            Samsung 49" Ultrawide (5120x1440)         │  │  Alienware 25" │
  │                                                      │  │  (2560x1440)   │
  │   ┌─────────────────────┬─────────────────────┐      │  │                │
  │   │   A (ROG/Windows)   │  B (MacBook Pro)    │      │  │   A (ROG)      │
  │   │   Left half         │  Right half         │      │  │   Extended     │
  │   └─────────────────────┴─────────────────────┘      │  │                │
  └──────────────────────────────────────────────────────┘  └────────────────┘

      ┌──────────────┐    ┌──────────────────┐
      │ ROG Keyboard │    │ MacBook keyboard │
      └──────────────┘    └──────────────────┘

  LIVING ROOM (wall-mounted):
  ┌────────────────────────────────┐  ┌────────────────────────────────┐
  │   LG NanoCell 65" (4K)        │  │   Samsung Frame 65" (4K)      │
  │   Extended display / media    │  │   C (Mac Mini) / Ambient Art  │
  └────────────────────────────────┘  └────────────────────────────────┘

  CONNECTIONS:
    A (ROG)        → Ultrawide LEFT (USB-C/DP) + Alienware (HDMI)
    B (MacBook)    → Ultrawide RIGHT (TB4/DP)
    C (Mac Mini)   → Samsung Frame 65" (HDMI) [or headless]
    LG NanoCell    → Available for any node (HDMI from ROG or Mac Mini)
"""

    def load_defaults(self) -> None:
        """Register Jeremy's actual display setup."""
        for display in _jeremys_displays():
            self.register(display)


# ---------------------------------------------------------------------------
# Jeremy's display inventory
# ---------------------------------------------------------------------------

def _jeremys_displays() -> list[DisplaySpec]:
    """Jeremy's actual display setup."""
    displays: list[DisplaySpec] = []

    # 1. Samsung 49" Ultrawide — shared between A (left) and B (right)
    displays.append(DisplaySpec(
        display_id="ultrawide-49",
        name='Samsung 49" Ultrawide',
        display_type=DisplayType.MONITOR,
        manufacturer="Samsung",
        model="Odyssey CRG9 / G9",
        size_inches=49,
        resolution_width=5120,
        resolution_height=1440,
        refresh_rate_hz=120,
        hdr=True,
        panel_type="VA",
        connection=DisplayConnection.USB_C_DP,
        position=DisplayPosition.CENTER_LEFT,
        is_primary=True,
        split_between_nodes=True,
        split_node_left="rog",
        split_node_right="macbook-pro",
        notes="PBP mode: left half = ROG (USB-C/DP), right half = MacBook (TB4/DP). "
              "Each side effectively 2560x1440.",
    ))

    # 2. Alienware 25" — secondary for ROG
    displays.append(DisplaySpec(
        display_id="alienware-25",
        name='Alienware 25" Gaming Monitor',
        display_type=DisplayType.MONITOR,
        manufacturer="Alienware (Dell)",
        model="AW2523HF",
        size_inches=25,
        resolution_width=2560,
        resolution_height=1440,
        refresh_rate_hz=240,
        hdr=False,
        panel_type="IPS",
        connection=DisplayConnection.HDMI,
        connected_to_node="rog",
        position=DisplayPosition.RIGHT,
        notes="High refresh rate secondary monitor for ROG. HDMI from ROG.",
    ))

    # 3. LG NanoCell 65" — wall-mounted TV
    displays.append(DisplaySpec(
        display_id="lg-nanocell-65",
        name='LG NanoCell 65" 4K TV',
        display_type=DisplayType.TV,
        manufacturer="LG",
        model="NanoCell 65",
        size_inches=65,
        resolution_width=3840,
        resolution_height=2160,
        refresh_rate_hz=60,
        hdr=True,
        panel_type="NanoCell IPS",
        connection=DisplayConnection.HDMI,
        connected_to_node="",  # Flexible — any node can drive it
        position=DisplayPosition.WALL_LEFT,
        supports_cec=True,
        auto_off_minutes=30,
        notes="Living room wall. Can extend from ROG or Mac Mini via HDMI. "
              "CEC enabled for power control.",
    ))

    # 4. Samsung Frame 65" — wall-mounted, Mac Mini primary output
    displays.append(DisplaySpec(
        display_id="samsung-frame-65",
        name='Samsung Frame 65" 4K TV',
        display_type=DisplayType.TV,
        manufacturer="Samsung",
        model="The Frame 65 (2023)",
        size_inches=65,
        resolution_width=3840,
        resolution_height=2160,
        refresh_rate_hz=60,
        hdr=True,
        panel_type="QLED",
        connection=DisplayConnection.HDMI,
        connected_to_node="mac-mini",
        position=DisplayPosition.WALL_RIGHT,
        supports_cec=True,
        auto_off_minutes=60,
        notes="Living room wall. Mac Mini (C) primary display. "
              "Art Mode when idle. HDMI-CEC for automated power control.",
    ))

    return displays
