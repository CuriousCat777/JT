"""Data Platform Connectors — Databricks, Zapier Tables, Notion Databases.

The Archivist's external memory. Three platforms, one pattern:
create → map → monitor → record.

Every write, read, schema change, and sync gets logged to the audit trail.
The Archivist creates the tables/databases, maps fields between them,
monitors for changes, and records all activity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PlatformType(Enum):
    DATABRICKS = "databricks"
    ZAPIER_TABLES = "zapier_tables"
    NOTION_DB = "notion_db"


class SyncDirection(Enum):
    PUSH = "push"        # Archivist → Platform
    PULL = "pull"        # Platform → Archivist
    BIDIRECTIONAL = "bidirectional"


@dataclass
class FieldMapping:
    """Maps a field between the Archivist's internal schema and a platform."""
    source_field: str
    target_field: str
    transform: str | None = None  # e.g., "uppercase", "date_iso", "encrypt"


@dataclass
class TableSchema:
    """Schema definition for a table/database on a platform."""
    name: str
    platform: PlatformType
    fields: dict[str, str] = field(default_factory=dict)  # field_name → type
    primary_key: str = "id"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class PlatformConnection:
    """A connection to an external data platform."""
    name: str
    platform: PlatformType
    endpoint: str                   # API base URL or connection string
    credential_key: str             # Vault key for auth token
    enabled: bool = True
    sync_direction: SyncDirection = SyncDirection.PUSH
    tables: dict[str, TableSchema] = field(default_factory=dict)
    last_sync: str | None = None
    sync_interval_minutes: int = 15
    activity_log: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ActivityRecord:
    """A single activity record — every operation gets one of these."""
    platform: str
    table: str
    operation: str          # create_table, insert, update, delete, schema_change, sync
    record_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DataPlatformManager:
    """Manages connections to Databricks, Zapier Tables, and Notion DBs.

    The Archivist's pattern for every platform:
    1. CREATE — set up tables/databases with defined schemas
    2. MAP    — field mappings between internal and external schemas
    3. MONITOR — track changes, schema drift, sync failures
    4. RECORD  — immutable activity log of every operation
    """

    def __init__(self) -> None:
        self._connections: dict[str, PlatformConnection] = {}
        self._mappings: dict[str, list[FieldMapping]] = {}  # table_key → mappings
        self._activity: list[ActivityRecord] = []

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def register_connection(self, conn: PlatformConnection) -> None:
        self._connections[conn.name] = conn

    def get_connection(self, name: str) -> PlatformConnection | None:
        return self._connections.get(name)

    def list_connections(self) -> list[str]:
        return list(self._connections.keys())

    def active_connections(self) -> list[PlatformConnection]:
        return [c for c in self._connections.values() if c.enabled]

    # ------------------------------------------------------------------
    # Table / schema management (CREATE)
    # ------------------------------------------------------------------

    def create_table(
        self,
        connection_name: str,
        schema: TableSchema,
    ) -> dict[str, Any]:
        """Register a table schema on a platform connection."""
        conn = self._connections.get(connection_name)
        if conn is None:
            return {"error": f"Unknown connection: {connection_name}"}

        conn.tables[schema.name] = schema
        self._record_activity(ActivityRecord(
            platform=connection_name,
            table=schema.name,
            operation="create_table",
            details={"fields": schema.fields, "primary_key": schema.primary_key},
        ))
        return {"status": "created", "table": schema.name, "platform": connection_name}

    def get_table_schema(self, connection_name: str, table_name: str) -> TableSchema | None:
        conn = self._connections.get(connection_name)
        if conn is None:
            return None
        return conn.tables.get(table_name)

    # ------------------------------------------------------------------
    # Field mapping (MAP)
    # ------------------------------------------------------------------

    def set_mappings(
        self,
        connection_name: str,
        table_name: str,
        mappings: list[FieldMapping],
    ) -> None:
        """Define field mappings between internal schema and a platform table."""
        key = f"{connection_name}:{table_name}"
        self._mappings[key] = mappings
        self._record_activity(ActivityRecord(
            platform=connection_name,
            table=table_name,
            operation="set_mappings",
            details={"mapping_count": len(mappings)},
        ))

    def get_mappings(self, connection_name: str, table_name: str) -> list[FieldMapping]:
        key = f"{connection_name}:{table_name}"
        return self._mappings.get(key, [])

    # ------------------------------------------------------------------
    # Sync simulation (MONITOR)
    # ------------------------------------------------------------------

    def sync_table(
        self,
        connection_name: str,
        table_name: str,
        records: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Simulate syncing records to/from a platform table.

        In production, this calls the platform API via the Gateway.
        In tests, it logs the operation and returns a summary.
        """
        conn = self._connections.get(connection_name)
        if conn is None:
            return {"error": f"Unknown connection: {connection_name}"}

        table = conn.tables.get(table_name)
        if table is None:
            return {"error": f"Unknown table: {table_name}"}

        record_count = len(records) if records else 0
        conn.last_sync = datetime.now(timezone.utc).isoformat()

        self._record_activity(ActivityRecord(
            platform=connection_name,
            table=table_name,
            operation="sync",
            record_count=record_count,
            details={
                "direction": conn.sync_direction.value,
                "records": record_count,
            },
        ))

        return {
            "status": "synced",
            "platform": connection_name,
            "table": table_name,
            "direction": conn.sync_direction.value,
            "records_synced": record_count,
            "synced_at": conn.last_sync,
        }

    # ------------------------------------------------------------------
    # Activity recording (RECORD)
    # ------------------------------------------------------------------

    def _record_activity(self, record: ActivityRecord) -> None:
        self._activity.append(record)

    def activity_log(
        self,
        platform: str | None = None,
        limit: int = 50,
    ) -> list[ActivityRecord]:
        """Get activity records, optionally filtered by platform."""
        records = self._activity
        if platform:
            records = [r for r in records if r.platform == platform]
        return records[-limit:]

    def activity_summary(self) -> dict[str, Any]:
        """Summary of all platform activity."""
        by_platform: dict[str, int] = {}
        by_operation: dict[str, int] = {}
        for record in self._activity:
            by_platform[record.platform] = by_platform.get(record.platform, 0) + 1
            by_operation[record.operation] = by_operation.get(record.operation, 0) + 1

        return {
            "total_operations": len(self._activity),
            "by_platform": by_platform,
            "by_operation": by_operation,
            "connections": len(self._connections),
            "active_connections": len(self.active_connections()),
        }

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def health_check(self) -> dict[str, Any]:
        """Check connectivity and sync status across all platforms."""
        statuses: dict[str, dict[str, Any]] = {}
        for name, conn in self._connections.items():
            statuses[name] = {
                "platform": conn.platform.value,
                "enabled": conn.enabled,
                "tables": len(conn.tables),
                "last_sync": conn.last_sync,
                "sync_direction": conn.sync_direction.value,
            }
        return {
            "platforms": statuses,
            "total_tables": sum(len(c.tables) for c in self._connections.values()),
            "activity_count": len(self._activity),
        }


# ------------------------------------------------------------------
# Default platform configurations
# ------------------------------------------------------------------

def default_databricks() -> PlatformConnection:
    return PlatformConnection(
        name="databricks",
        platform=PlatformType.DATABRICKS,
        endpoint="https://workspace.cloud.databricks.com/api/2.0",
        credential_key="DATABRICKS_TOKEN",
        sync_direction=SyncDirection.PUSH,
    )


def default_zapier_tables() -> PlatformConnection:
    return PlatformConnection(
        name="zapier_tables",
        platform=PlatformType.ZAPIER_TABLES,
        endpoint="https://tables.zapier.com/api/v1",
        credential_key="ZAPIER_TABLES_TOKEN",
        sync_direction=SyncDirection.BIDIRECTIONAL,
    )


def default_notion_db() -> PlatformConnection:
    return PlatformConnection(
        name="notion_db",
        platform=PlatformType.NOTION_DB,
        endpoint="https://api.notion.com/v1",
        credential_key="NOTION_TOKEN",
        sync_direction=SyncDirection.PUSH,  # Write-only per Guardian policy
    )
