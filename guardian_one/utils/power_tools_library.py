"""Power Tools Library — shared agent access to Rails + Gin tooling.

This library is managed by the Archivist and provides any authorized agent
with the ability to discover, scaffold, and manage Rails and Gin projects.

The library tracks all projects as Archivist-managed file records, ensuring
data sovereignty and audit trails for every framework operation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guardian_one.core.audit import AuditLog, Severity
from guardian_one.integrations.rails_gin import (
    FrameworkType,
    ProjectInfo,
    ToolStatus,
    check_gin,
    check_go,
    check_rails,
    check_ruby,
    install_gin,
    install_rails,
    power_tools_status,
    scaffold_gin,
    scaffold_rails,
    start_gin_server,
    start_rails_server,
)


@dataclass
class ManagedProject:
    """A framework project tracked by the library."""
    info: ProjectInfo
    managed_by: str = "archivist"
    tags: list[str] = field(default_factory=list)
    last_action: str = ""
    last_action_by: str = ""
    last_action_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PowerToolsLibrary:
    """Shared library giving agents access to Rails + Gin power tools.

    Managed by the Archivist agent.  Any agent whose ``allowed_resources``
    includes ``"power_tools"`` can call methods on this library.  All
    operations are audit-logged and projects are tracked as managed records.

    Usage (from an agent):
        lib = self._power_tools  # injected by GuardianOne
        status = lib.status()
        result = lib.create_rails_app("my_app", requester="web_architect")
        result = lib.create_gin_app("my_api", requester="web_architect")
    """

    def __init__(self, audit: AuditLog, data_dir: str = "data") -> None:
        self._audit = audit
        self._data_dir = Path(data_dir)
        self._projects: dict[str, ManagedProject] = {}
        self._manifest_path = self._data_dir / "power_tools_manifest.json"
        self._load_manifest()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_manifest(self) -> None:
        """Load project manifest from disk."""
        if self._manifest_path.exists():
            try:
                raw = json.loads(self._manifest_path.read_text())
                for name, data in raw.get("projects", {}).items():
                    info = ProjectInfo(
                        name=data["name"],
                        framework=FrameworkType(data["framework"]),
                        path=data["path"],
                        created_at=data.get("created_at", ""),
                        port=data.get("port", 0),
                    )
                    self._projects[name] = ManagedProject(
                        info=info,
                        managed_by=data.get("managed_by", "archivist"),
                        tags=data.get("tags", []),
                        last_action=data.get("last_action", ""),
                        last_action_by=data.get("last_action_by", ""),
                        last_action_at=data.get("last_action_at", ""),
                    )
            except (json.JSONDecodeError, KeyError):
                self._projects = {}

    def _save_manifest(self) -> None:
        """Persist project manifest to disk."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {"projects": {}}
        for name, mp in self._projects.items():
            data["projects"][name] = {
                "name": mp.info.name,
                "framework": mp.info.framework.value,
                "path": mp.info.path,
                "created_at": mp.info.created_at,
                "port": mp.info.port,
                "managed_by": mp.managed_by,
                "tags": mp.tags,
                "last_action": mp.last_action,
                "last_action_by": mp.last_action_by,
                "last_action_at": mp.last_action_at,
            }
        self._manifest_path.write_text(json.dumps(data, indent=2))

    def _log(
        self,
        action: str,
        requester: str,
        severity: Severity = Severity.INFO,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._audit.record(
            agent=f"power_tools/{requester}",
            action=action,
            severity=severity,
            details=details or {},
        )

    # ------------------------------------------------------------------
    # Status & discovery
    # ------------------------------------------------------------------

    def status(self, requester: str = "system") -> dict[str, Any]:
        """Return full power tools status including managed projects."""
        base = power_tools_status()
        base["managed_projects"] = {
            name: {
                "framework": mp.info.framework.value,
                "path": mp.info.path,
                "port": mp.info.port,
                "managed_by": mp.managed_by,
                "tags": mp.tags,
                "last_action": mp.last_action,
                "last_action_by": mp.last_action_by,
            }
            for name, mp in self._projects.items()
        }
        self._log("status_check", requester)
        return base

    def list_projects(
        self,
        framework: FrameworkType | None = None,
        tags: list[str] | None = None,
    ) -> list[ManagedProject]:
        """List managed projects, optionally filtered."""
        results = list(self._projects.values())
        if framework:
            results = [p for p in results if p.info.framework == framework]
        if tags:
            tag_set = set(tags)
            results = [p for p in results if tag_set.intersection(p.tags)]
        return results

    def get_project(self, name: str) -> ManagedProject | None:
        return self._projects.get(name)

    # ------------------------------------------------------------------
    # Rails operations
    # ------------------------------------------------------------------

    def create_rails_app(
        self,
        app_name: str,
        requester: str = "archivist",
        parent_dir: str | None = None,
        api_only: bool = False,
        database: str = "sqlite3",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Scaffold a new Rails app and register it in the library.

        Args:
            app_name: Name of the application.
            requester: Agent requesting the operation.
            parent_dir: Directory to create in (defaults to cwd).
            api_only: API-only mode.
            database: Database adapter.
            tags: Tags for categorization.

        Returns:
            Result dict with project info.
        """
        self._log("rails_scaffold_start", requester, details={
            "app_name": app_name, "api_only": api_only, "database": database,
        })

        result = scaffold_rails(
            app_name=app_name,
            parent_dir=parent_dir,
            api_only=api_only,
            database=database,
        )

        if result.get("success"):
            project_info = result["project"]
            managed = ManagedProject(
                info=project_info,
                managed_by="archivist",
                tags=tags or ["rails", "web"],
                last_action="created",
                last_action_by=requester,
            )
            self._projects[app_name] = managed
            self._save_manifest()
            self._log("rails_scaffold_complete", requester, details={
                "app_name": app_name, "path": result["path"],
            })
            result["managed"] = True
        else:
            self._log("rails_scaffold_failed", requester,
                       severity=Severity.WARNING,
                       details={"app_name": app_name, "error": result.get("error")})
            result["managed"] = False

        return result

    def install_rails_gem(self, requester: str = "archivist") -> dict[str, Any]:
        """Install Ruby on Rails via gem, tracked by the library."""
        self._log("rails_install_start", requester)
        result = install_rails()
        if result.get("success"):
            self._log("rails_install_complete", requester, details={
                "version": result.get("version", ""),
            })
        else:
            self._log("rails_install_failed", requester,
                       severity=Severity.WARNING,
                       details={"error": result.get("error")})
        return result

    def start_rails(
        self,
        app_name: str,
        requester: str = "web_architect",
        port: int = 3000,
    ) -> dict[str, Any]:
        """Start a managed Rails app server."""
        project = self._projects.get(app_name)
        if not project:
            return {"success": False, "error": f"Unknown project: {app_name}"}
        if project.info.framework != FrameworkType.RAILS:
            return {"success": False, "error": f"{app_name} is not a Rails project"}

        result = start_rails_server(project.info.path, port=port)
        if result.get("success"):
            project.info.pid = result["pid"]
            project.info.running = True
            project.info.port = port
            project.last_action = "server_started"
            project.last_action_by = requester
            project.last_action_at = datetime.now(timezone.utc).isoformat()
            self._save_manifest()
            self._log("rails_server_started", requester, details={
                "app": app_name, "port": port, "pid": result["pid"],
            })
        return result

    # ------------------------------------------------------------------
    # Gin operations
    # ------------------------------------------------------------------

    def create_gin_app(
        self,
        app_name: str,
        requester: str = "archivist",
        parent_dir: str | None = None,
        module_path: str | None = None,
        port: int = 8080,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Scaffold a new Gin app and register it in the library.

        Args:
            app_name: Name of the application.
            requester: Agent requesting the operation.
            parent_dir: Directory to create in (defaults to cwd).
            module_path: Go module path.
            port: Default server port.
            tags: Tags for categorization.

        Returns:
            Result dict with project info.
        """
        self._log("gin_scaffold_start", requester, details={
            "app_name": app_name, "module": module_path, "port": port,
        })

        result = scaffold_gin(
            app_name=app_name,
            parent_dir=parent_dir,
            module_path=module_path,
            port=port,
        )

        if result.get("success"):
            project_info = result["project"]
            managed = ManagedProject(
                info=project_info,
                managed_by="archivist",
                tags=tags or ["gin", "go", "api"],
                last_action="created",
                last_action_by=requester,
            )
            self._projects[app_name] = managed
            self._save_manifest()
            self._log("gin_scaffold_complete", requester, details={
                "app_name": app_name, "path": result["path"],
            })
            result["managed"] = True
        else:
            self._log("gin_scaffold_failed", requester,
                       severity=Severity.WARNING,
                       details={"app_name": app_name, "error": result.get("error")})
            result["managed"] = False

        return result

    def start_gin(
        self,
        app_name: str,
        requester: str = "web_architect",
        port: int = 8080,
    ) -> dict[str, Any]:
        """Start a managed Gin app server."""
        project = self._projects.get(app_name)
        if not project:
            return {"success": False, "error": f"Unknown project: {app_name}"}
        if project.info.framework != FrameworkType.GIN:
            return {"success": False, "error": f"{app_name} is not a Gin project"}

        result = start_gin_server(project.info.path, port=port)
        if result.get("success"):
            project.info.pid = result["pid"]
            project.info.running = True
            project.info.port = port
            project.last_action = "server_started"
            project.last_action_by = requester
            project.last_action_at = datetime.now(timezone.utc).isoformat()
            self._save_manifest()
            self._log("gin_server_started", requester, details={
                "app": app_name, "port": port, "pid": result["pid"],
            })
        return result

    # ------------------------------------------------------------------
    # Project management (Archivist domain)
    # ------------------------------------------------------------------

    def tag_project(
        self, name: str, tags: list[str], requester: str = "archivist"
    ) -> bool:
        """Add tags to a managed project."""
        project = self._projects.get(name)
        if not project:
            return False
        project.tags = list(set(project.tags + tags))
        project.last_action = "tagged"
        project.last_action_by = requester
        project.last_action_at = datetime.now(timezone.utc).isoformat()
        self._save_manifest()
        return True

    def remove_project(self, name: str, requester: str = "archivist") -> bool:
        """Remove a project from the managed library (does not delete files)."""
        if name not in self._projects:
            return False
        self._log("project_removed", requester, details={"project": name})
        del self._projects[name]
        self._save_manifest()
        return True

    def summary_text(self) -> str:
        """Human-readable summary of the power tools library."""
        lines = [
            "  POWER TOOLS LIBRARY",
            "  " + "=" * 50,
        ]

        status = power_tools_status()
        lines.append(f"  Ruby:   {status['ruby']['status']:<16} {status['ruby']['version']}")
        lines.append(f"  Rails:  {status['rails']['status']:<16} {status['rails']['version']}")
        lines.append(f"  Go:     {status['go']['status']:<16} {status['go']['version']}")
        lines.append(f"  Gin:    {status['gin']['status']:<16} {status['gin'].get('note', '')}")
        lines.append("")

        if self._projects:
            lines.append(f"  MANAGED PROJECTS ({len(self._projects)})")
            lines.append("  " + "-" * 50)
            for name, mp in self._projects.items():
                fw = mp.info.framework.value.upper()
                port_str = f":{mp.info.port}" if mp.info.port else ""
                running = " [RUNNING]" if mp.info.running else ""
                tags_str = f"  [{', '.join(mp.tags)}]" if mp.tags else ""
                lines.append(f"    {fw:5s} {name}{port_str}{running}{tags_str}")
                lines.append(f"          path: {mp.info.path}")
                lines.append(f"          managed by: {mp.managed_by}")
        else:
            lines.append("  No managed projects yet.")
            lines.append("  Use --rails-new or --gin-new to scaffold one.")

        lines.append("")
        return "\n".join(lines)
