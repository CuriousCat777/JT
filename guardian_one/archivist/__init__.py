"""Archivist Subsystems — central telemetry, tech detection, cloud sync.

Extends the Archivist agent into a full data sovereignty platform:
- TelemetryHub: central cross-system event logging
- TechDetector: auto-detect new technology/services/accounts
- CloudSync: multi-cloud backup portals
- Persistence: durable JSON state on disk + Vault integration
"""

from guardian_one.archivist.telemetry import TelemetryHub, TelemetryEvent
from guardian_one.archivist.techdetect import TechDetector, TechRecord
from guardian_one.archivist.cloudsync import CloudSync, CloudTarget
from guardian_one.archivist.file_organizer import FileOrganizer, CleanupRule
from guardian_one.archivist.account_manager import AccountManager, AccountRecord
from guardian_one.archivist.password_sync import PasswordSync, VaultItem

__all__ = [
    "TelemetryHub",
    "TelemetryEvent",
    "TechDetector",
    "TechRecord",
    "CloudSync",
    "CloudTarget",
    "FileOrganizer",
    "CleanupRule",
    "AccountManager",
    "AccountRecord",
    "PasswordSync",
    "VaultItem",
]
