"""Rails + Gin Power Tools — web framework scaffolding & management.

Provides Guardian One with the ability to scaffold, build, and manage
Ruby on Rails and Go Gin web projects.  Both frameworks are offered as
power-tool options for Jeremy's web properties and internal tooling.

Usage (via CLI):
    python main.py --power-tools                # Show status of Rails & Gin tools
    python main.py --rails-new APP_NAME          # Scaffold a new Rails application
    python main.py --gin-new APP_NAME            # Scaffold a new Gin application
    python main.py --rails-server APP_PATH       # Start a Rails dev server
    python main.py --gin-server APP_PATH         # Start a Gin dev server
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class FrameworkType(Enum):
    RAILS = "rails"
    GIN = "gin"


class ToolStatus(Enum):
    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"
    ERROR = "error"


@dataclass
class FrameworkInfo:
    """Runtime status of a framework installation."""
    framework: FrameworkType
    status: ToolStatus
    version: str = ""
    path: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectInfo:
    """Metadata for a scaffolded project."""
    name: str
    framework: FrameworkType
    path: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    port: int = 0
    pid: int | None = None
    running: bool = False


# ---------------------------------------------------------------------------
# Dependency detection
# ---------------------------------------------------------------------------

def _run_cmd(cmd: list[str], timeout: int = 30, cwd: str | None = None) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", f"command timed out after {timeout}s"


def check_ruby() -> FrameworkInfo:
    """Check if Ruby is installed."""
    rc, out, err = _run_cmd(["ruby", "--version"])
    if rc == 0:
        return FrameworkInfo(
            framework=FrameworkType.RAILS,
            status=ToolStatus.INSTALLED,
            version=out,
            path=shutil.which("ruby") or "",
        )
    return FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.NOT_INSTALLED,
        details={"error": err},
    )


def check_rails() -> FrameworkInfo:
    """Check if Ruby on Rails is installed."""
    rc, out, err = _run_cmd(["rails", "--version"])
    if rc == 0:
        return FrameworkInfo(
            framework=FrameworkType.RAILS,
            status=ToolStatus.INSTALLED,
            version=out,
            path=shutil.which("rails") or "",
        )
    return FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.NOT_INSTALLED,
        details={"error": err},
    )


def check_go() -> FrameworkInfo:
    """Check if Go is installed."""
    rc, out, err = _run_cmd(["go", "version"])
    if rc == 0:
        return FrameworkInfo(
            framework=FrameworkType.GIN,
            status=ToolStatus.INSTALLED,
            version=out,
            path=shutil.which("go") or "",
        )
    return FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.NOT_INSTALLED,
        details={"error": err},
    )


def check_gin() -> FrameworkInfo:
    """Check if Gin is available (Go module).

    Gin is a Go module installed per-project via ``go get``, so we only
    verify that Go itself is present.  Gin availability is project-scoped
    and resolved at scaffold/install time.
    """
    go_info = check_go()
    if go_info.status != ToolStatus.INSTALLED:
        return FrameworkInfo(
            framework=FrameworkType.GIN,
            status=ToolStatus.NOT_INSTALLED,
            details={"error": "Go is not installed — Gin requires Go"},
        )
    return FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.INSTALLED,
        version=go_info.version,
        path=go_info.path,
        details={"note": "Gin installs per-project via go module"},
    )


# ---------------------------------------------------------------------------
# Installation helpers
# ---------------------------------------------------------------------------

def install_rails() -> dict[str, Any]:
    """Install Ruby on Rails via gem.

    Returns a result dict with status and output.
    Requires Ruby + gem to already be present.
    """
    ruby = check_ruby()
    if ruby.status != ToolStatus.INSTALLED:
        return {
            "success": False,
            "error": "Ruby is not installed. Install Ruby first (https://www.ruby-lang.org).",
        }

    # Check if rails already installed
    existing = check_rails()
    if existing.status == ToolStatus.INSTALLED:
        return {
            "success": True,
            "already_installed": True,
            "version": existing.version,
        }

    rc, out, err = _run_cmd(["gem", "install", "rails"], timeout=300)
    if rc == 0:
        rails = check_rails()
        return {
            "success": True,
            "already_installed": False,
            "version": rails.version,
            "output": out,
        }
    return {"success": False, "error": err or out}


def install_gin(project_dir: str) -> dict[str, Any]:
    """Add Gin to a Go project via `go get`.

    Args:
        project_dir: Path to a Go module directory (must have go.mod).

    Returns a result dict with status and output.
    """
    go = check_go()
    if go.status != ToolStatus.INSTALLED:
        return {
            "success": False,
            "error": "Go is not installed. Install Go first (https://go.dev/dl).",
        }

    project = Path(project_dir)
    if not (project / "go.mod").exists():
        return {
            "success": False,
            "error": f"No go.mod found in {project_dir}. Run 'go mod init' first.",
        }

    rc, out, err = _run_cmd(
        ["go", "get", "-u", "github.com/gin-gonic/gin"],
        timeout=120,
        cwd=project_dir,
    )
    if rc == 0:
        return {"success": True, "output": out or "gin installed"}
    return {"success": False, "error": err or out}


# ---------------------------------------------------------------------------
# Project scaffolding
# ---------------------------------------------------------------------------

def scaffold_rails(
    app_name: str,
    parent_dir: str | None = None,
    api_only: bool = False,
    database: str = "sqlite3",
) -> dict[str, Any]:
    """Scaffold a new Rails application.

    Args:
        app_name: Name of the Rails application.
        parent_dir: Directory to create the app in (defaults to cwd).
        api_only: If True, generate an API-only Rails app (--api).
        database: Database adapter (sqlite3, postgresql, mysql).

    Returns result dict with project path and status.
    """
    rails_info = check_rails()
    if rails_info.status != ToolStatus.INSTALLED:
        return {
            "success": False,
            "error": "Rails is not installed. Run install_rails() first.",
        }

    base = Path(parent_dir) if parent_dir else Path.cwd()
    target = base / app_name

    if target.exists():
        return {
            "success": False,
            "error": f"Directory already exists: {target}",
        }

    cmd = ["rails", "new", str(target), f"--database={database}"]
    if api_only:
        cmd.append("--api")

    rc, out, err = _run_cmd(cmd, timeout=600)
    if rc == 0 and target.exists():
        return {
            "success": True,
            "path": str(target),
            "project": ProjectInfo(
                name=app_name,
                framework=FrameworkType.RAILS,
                path=str(target),
                port=3000,
            ),
            "output": out[-500:] if len(out) > 500 else out,
        }
    return {"success": False, "error": err or out or "rails new failed"}


def scaffold_gin(
    app_name: str,
    parent_dir: str | None = None,
    module_path: str | None = None,
    port: int = 8080,
) -> dict[str, Any]:
    """Scaffold a new Gin (Go) application with a starter template.

    Creates a Go module, installs Gin, and writes a minimal main.go
    with health-check, CORS middleware, and example route groups.

    Args:
        app_name: Name of the application directory.
        parent_dir: Directory to create the app in (defaults to cwd).
        module_path: Go module path (defaults to app_name).
        port: Default port for the Gin server.

    Returns result dict with project path and status.
    """
    go_info = check_go()
    if go_info.status != ToolStatus.INSTALLED:
        return {
            "success": False,
            "error": "Go is not installed. Install Go first (https://go.dev/dl).",
        }

    base = Path(parent_dir) if parent_dir else Path.cwd()
    target = base / app_name

    if target.exists():
        return {
            "success": False,
            "error": f"Directory already exists: {target}",
        }

    target.mkdir(parents=True)
    mod = module_path or app_name

    # Initialize Go module
    rc, out, err = _run_cmd(["go", "mod", "init", mod], timeout=30, cwd=str(target))
    if rc != 0:
        shutil.rmtree(target, ignore_errors=True)
        return {"success": False, "error": f"go mod init failed: {err}"}

    # Write main.go
    main_go = _gin_main_template(mod, port)
    (target / "main.go").write_text(main_go)

    # Write routes
    (target / "routes").mkdir()
    (target / "routes" / "api.go").write_text(_gin_routes_template(mod))

    # Write middleware
    (target / "middleware").mkdir()
    (target / "middleware" / "cors.go").write_text(_gin_cors_template(mod))

    # Install Gin dependency
    gin_result = install_gin(str(target))
    if not gin_result["success"]:
        return {
            "success": False,
            "error": f"Gin install failed: {gin_result['error']}",
            "path": str(target),
        }

    # Tidy modules
    _run_cmd(["go", "mod", "tidy"], timeout=60, cwd=str(target))

    return {
        "success": True,
        "path": str(target),
        "project": ProjectInfo(
            name=app_name,
            framework=FrameworkType.GIN,
            path=str(target),
            port=port,
        ),
    }


# ---------------------------------------------------------------------------
# Server management
# ---------------------------------------------------------------------------

def start_rails_server(
    app_path: str,
    port: int = 3000,
    environment: str = "development",
) -> dict[str, Any]:
    """Start a Rails development server (non-blocking).

    Args:
        app_path: Path to the Rails application root.
        port: Port number (default 3000).
        environment: Rails environment (development/test/production).

    Returns dict with pid and status.
    """
    app = Path(app_path)
    if not (app / "Gemfile").exists():
        return {"success": False, "error": f"Not a Rails app: {app_path}"}

    try:
        proc = subprocess.Popen(
            ["rails", "server", "-p", str(port), "-e", environment],
            cwd=str(app),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "success": True,
            "pid": proc.pid,
            "port": port,
            "environment": environment,
            "url": f"http://localhost:{port}",
        }
    except FileNotFoundError:
        return {"success": False, "error": "rails command not found"}
    except OSError as exc:
        return {"success": False, "error": str(exc)}


def start_gin_server(
    app_path: str,
    port: int = 8080,
) -> dict[str, Any]:
    """Start a Gin development server via `go run` (non-blocking).

    Args:
        app_path: Path to the Go application root.
        port: Port number (default 8080).

    Returns dict with pid and status.
    """
    app = Path(app_path)
    if not (app / "main.go").exists():
        return {"success": False, "error": f"No main.go found in {app_path}"}

    env = os.environ.copy()
    env["PORT"] = str(port)

    try:
        proc = subprocess.Popen(
            ["go", "run", "."],
            cwd=str(app),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        return {
            "success": True,
            "pid": proc.pid,
            "port": port,
            "url": f"http://localhost:{port}",
        }
    except FileNotFoundError:
        return {"success": False, "error": "go command not found"}
    except OSError as exc:
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Power tools status
# ---------------------------------------------------------------------------

def power_tools_status() -> dict[str, Any]:
    """Return a comprehensive status of the Rails + Gin power tools."""
    ruby = check_ruby()
    rails = check_rails()
    go = check_go()
    gin = check_gin()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ruby": {
            "status": ruby.status.value,
            "version": ruby.version,
            "path": ruby.path,
        },
        "rails": {
            "status": rails.status.value,
            "version": rails.version,
            "path": rails.path,
        },
        "go": {
            "status": go.status.value,
            "version": go.version,
            "path": go.path,
        },
        "gin": {
            "status": gin.status.value,
            "version": gin.version,
            "note": gin.details.get("note", ""),
        },
        "capabilities": {
            "rails": [
                "scaffold new Rails apps (full-stack or API-only)",
                "start/stop Rails dev servers",
                "database adapters: sqlite3, postgresql, mysql",
                "integrates with Guardian One web properties",
            ],
            "gin": [
                "scaffold new Gin apps with starter template",
                "CORS middleware, health checks, route groups",
                "start/stop Gin dev servers",
                "high-performance Go API backend",
                "pairs with Rails frontend or standalone",
            ],
        },
        "use_cases": {
            "rails_frontend_gin_api": (
                "Rails handles views, assets, and sessions while "
                "Gin serves as a high-performance JSON API backend."
            ),
            "rails_full_stack": (
                "Traditional Rails monolith for rapid prototyping "
                "with built-in ORM, migrations, and view templates."
            ),
            "gin_microservice": (
                "Lightweight Go microservice with Gin for "
                "latency-critical endpoints and system integrations."
            ),
            "guardian_one_api": (
                "Gin API layer in front of Guardian One agents, "
                "offering typed Go endpoints with low overhead."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Gin project templates
# ---------------------------------------------------------------------------

def _gin_main_template(module: str, port: int) -> str:
    return f'''package main

import (
\t"fmt"
\t"log"
\t"os"

\t"github.com/gin-gonic/gin"
\t"{module}/middleware"
\t"{module}/routes"
)

func main() {{
\tport := os.Getenv("PORT")
\tif port == "" {{
\t\tport = "{port}"
\t}}

\tr := gin.Default()

\t// Middleware
\tr.Use(middleware.CORS())

\t// Health check
\tr.GET("/health", func(c *gin.Context) {{
\t\tc.JSON(200, gin.H{{
\t\t\t"status":  "ok",
\t\t\t"service": "{module}",
\t\t}})
\t}})

\t// Register route groups
\troutes.RegisterAPI(r)

\taddr := fmt.Sprintf(":%s", port)
\tlog.Printf("Starting %s on %s", "{module}", addr)
\tif err := r.Run(addr); err != nil {{
\t\tlog.Fatalf("Server failed: %v", err)
\t}}
}}
'''


def _gin_routes_template(module: str) -> str:
    return f'''package routes

import (
\t"net/http"

\t"github.com/gin-gonic/gin"
)

// RegisterAPI sets up the /api/v1 route group.
func RegisterAPI(r *gin.Engine) {{
\tv1 := r.Group("/api/v1")
\t{{
\t\tv1.GET("/ping", func(c *gin.Context) {{
\t\t\tc.JSON(http.StatusOK, gin.H{{"message": "pong"}})
\t\t}})

\t\tv1.GET("/status", func(c *gin.Context) {{
\t\t\tc.JSON(http.StatusOK, gin.H{{
\t\t\t\t"service": "{module}",
\t\t\t\t"version": "0.1.0",
\t\t\t}})
\t\t}})
\t}}
}}
'''


def _gin_cors_template(module: str) -> str:
    return '''package middleware

import (
\t"github.com/gin-gonic/gin"
)

// CORS returns a middleware handler that sets CORS headers.
func CORS() gin.HandlerFunc {
\treturn func(c *gin.Context) {
\t\tc.Header("Access-Control-Allow-Origin", "*")
\t\tc.Header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
\t\tc.Header("Access-Control-Allow-Headers", "Origin, Content-Type, Authorization")

\t\tif c.Request.Method == "OPTIONS" {
\t\t\tc.AbortWithStatus(204)
\t\t\treturn
\t\t}

\t\tc.Next()
\t}
}
'''
