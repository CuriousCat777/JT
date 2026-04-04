"""Tests for Power Tools Library — agent access to Rails + Gin tooling.

All tests use mocks — no actual Ruby, Rails, Go, or Gin required.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.integrations.rails_gin import FrameworkType, ProjectInfo, ToolStatus
from guardian_one.utils.power_tools_library import ManagedProject, PowerToolsLibrary


@pytest.fixture
def audit():
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


@pytest.fixture
def data_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def library(audit, data_dir):
    return PowerToolsLibrary(audit=audit, data_dir=data_dir)


# ---------------------------------------------------------------
# Initialization & persistence
# ---------------------------------------------------------------

def test_library_init_empty(library):
    assert library.list_projects() == []


def test_manifest_persistence(audit, data_dir):
    lib = PowerToolsLibrary(audit=audit, data_dir=data_dir)

    # Manually insert a project
    lib._projects["test_app"] = ManagedProject(
        info=ProjectInfo(
            name="test_app",
            framework=FrameworkType.RAILS,
            path="/tmp/test_app",
            port=3000,
        ),
        tags=["rails", "test"],
    )
    lib._save_manifest()

    # Reload
    lib2 = PowerToolsLibrary(audit=audit, data_dir=data_dir)
    assert "test_app" in lib2._projects
    proj = lib2._projects["test_app"]
    assert proj.info.framework == FrameworkType.RAILS
    assert proj.info.port == 3000
    assert "rails" in proj.tags


def test_manifest_handles_corrupt_json(audit, data_dir):
    manifest = Path(data_dir) / "power_tools_manifest.json"
    manifest.write_text("not valid json {{{")
    lib = PowerToolsLibrary(audit=audit, data_dir=data_dir)
    assert lib.list_projects() == []


def test_manifest_persists_pid_and_running(audit, data_dir):
    lib = PowerToolsLibrary(audit=audit, data_dir=data_dir)
    lib._projects["app"] = ManagedProject(
        info=ProjectInfo(
            name="app", framework=FrameworkType.RAILS, path="/tmp/app",
            port=3000, pid=12345, running=True,
        ),
    )
    lib._save_manifest()

    # Reload — PID 12345 won't be alive, so running should be False
    lib2 = PowerToolsLibrary(audit=audit, data_dir=data_dir)
    proj = lib2._projects["app"]
    assert proj.info.running is False
    assert proj.info.pid is None  # Stale PID cleared


def test_manifest_skips_invalid_framework(audit, data_dir):
    manifest = Path(data_dir) / "power_tools_manifest.json"
    manifest.write_text(json.dumps({
        "projects": {
            "good": {
                "name": "good", "framework": "rails", "path": "/tmp/good",
            },
            "bad": {
                "name": "bad", "framework": "nonexistent_framework", "path": "/tmp/bad",
            },
        }
    }))
    lib = PowerToolsLibrary(audit=audit, data_dir=data_dir)
    assert "good" in lib._projects
    assert "bad" not in lib._projects  # Skipped, not crashed


# ---------------------------------------------------------------
# Status
# ---------------------------------------------------------------

@patch("guardian_one.utils.power_tools_library.power_tools_status")
def test_status_includes_managed_projects(mock_status, library):
    mock_status.return_value = {
        "ruby": {"status": "installed"},
        "rails": {"status": "installed"},
        "go": {"status": "installed"},
        "gin": {"status": "installed"},
    }
    library._projects["app1"] = ManagedProject(
        info=ProjectInfo(name="app1", framework=FrameworkType.RAILS, path="/tmp/app1"),
        tags=["rails"],
    )
    result = library.status(requester="archivist")
    assert "managed_projects" in result
    assert "app1" in result["managed_projects"]


# ---------------------------------------------------------------
# List & filter projects
# ---------------------------------------------------------------

def test_list_projects_by_framework(library):
    library._projects["rails_app"] = ManagedProject(
        info=ProjectInfo(name="rails_app", framework=FrameworkType.RAILS, path="/a"),
    )
    library._projects["gin_app"] = ManagedProject(
        info=ProjectInfo(name="gin_app", framework=FrameworkType.GIN, path="/b"),
    )

    rails_only = library.list_projects(framework=FrameworkType.RAILS)
    assert len(rails_only) == 1
    assert rails_only[0].info.name == "rails_app"

    gin_only = library.list_projects(framework=FrameworkType.GIN)
    assert len(gin_only) == 1
    assert gin_only[0].info.name == "gin_app"


def test_list_projects_by_tags(library):
    library._projects["app1"] = ManagedProject(
        info=ProjectInfo(name="app1", framework=FrameworkType.RAILS, path="/a"),
        tags=["production", "rails"],
    )
    library._projects["app2"] = ManagedProject(
        info=ProjectInfo(name="app2", framework=FrameworkType.GIN, path="/b"),
        tags=["staging", "gin"],
    )

    prod = library.list_projects(tags=["production"])
    assert len(prod) == 1
    assert prod[0].info.name == "app1"


def test_get_project(library):
    library._projects["myapp"] = ManagedProject(
        info=ProjectInfo(name="myapp", framework=FrameworkType.RAILS, path="/tmp/myapp"),
    )
    assert library.get_project("myapp") is not None
    assert library.get_project("nonexistent") is None


# ---------------------------------------------------------------
# Rails operations
# ---------------------------------------------------------------

@patch("guardian_one.utils.power_tools_library.scaffold_rails")
def test_create_rails_app_success(mock_scaffold, library):
    mock_scaffold.return_value = {
        "success": True,
        "path": "/tmp/my_rails_app",
        "project": ProjectInfo(
            name="my_rails_app",
            framework=FrameworkType.RAILS,
            path="/tmp/my_rails_app",
            port=3000,
        ),
    }
    result = library.create_rails_app("my_rails_app", requester="archivist")
    assert result["success"]
    assert result["managed"]
    assert "my_rails_app" in library._projects
    assert library._projects["my_rails_app"].managed_by == "archivist"
    assert library._projects["my_rails_app"].last_action_by == "archivist"


@patch("guardian_one.utils.power_tools_library.scaffold_rails")
def test_create_rails_app_failure(mock_scaffold, library):
    mock_scaffold.return_value = {
        "success": False,
        "error": "Rails not installed",
    }
    result = library.create_rails_app("my_rails_app", requester="web_architect")
    assert not result["success"]
    assert not result["managed"]
    assert "my_rails_app" not in library._projects


@patch("guardian_one.utils.power_tools_library.install_rails")
def test_install_rails_gem(mock_install, library):
    mock_install.return_value = {"success": True, "version": "Rails 7.1.3"}
    result = library.install_rails_gem(requester="archivist")
    assert result["success"]


@patch("guardian_one.utils.power_tools_library.start_rails_server")
def test_start_rails_success(mock_start, library):
    library._projects["myapp"] = ManagedProject(
        info=ProjectInfo(name="myapp", framework=FrameworkType.RAILS, path="/tmp/myapp"),
    )
    mock_start.return_value = {"success": True, "pid": 1234, "port": 3000}

    result = library.start_rails("myapp", requester="web_architect")
    assert result["success"]
    assert library._projects["myapp"].info.pid == 1234
    assert library._projects["myapp"].info.running
    assert library._projects["myapp"].last_action == "server_started"
    assert library._projects["myapp"].last_action_by == "web_architect"


def test_start_rails_unknown_project(library):
    result = library.start_rails("nonexistent")
    assert not result["success"]
    assert "Unknown" in result["error"]


def test_start_rails_wrong_framework(library):
    library._projects["gin_app"] = ManagedProject(
        info=ProjectInfo(name="gin_app", framework=FrameworkType.GIN, path="/tmp/gin"),
    )
    result = library.start_rails("gin_app")
    assert not result["success"]
    assert "not a Rails" in result["error"]


# ---------------------------------------------------------------
# Gin operations
# ---------------------------------------------------------------

@patch("guardian_one.utils.power_tools_library.scaffold_gin")
def test_create_gin_app_success(mock_scaffold, library):
    mock_scaffold.return_value = {
        "success": True,
        "path": "/tmp/my_gin_api",
        "project": ProjectInfo(
            name="my_gin_api",
            framework=FrameworkType.GIN,
            path="/tmp/my_gin_api",
            port=8080,
        ),
    }
    result = library.create_gin_app("my_gin_api", requester="web_architect", port=8080)
    assert result["success"]
    assert result["managed"]
    assert "my_gin_api" in library._projects
    assert library._projects["my_gin_api"].last_action_by == "web_architect"


@patch("guardian_one.utils.power_tools_library.scaffold_gin")
def test_create_gin_app_failure(mock_scaffold, library):
    mock_scaffold.return_value = {
        "success": False,
        "error": "Go not installed",
    }
    result = library.create_gin_app("my_api", requester="archivist")
    assert not result["success"]
    assert not result["managed"]


@patch("guardian_one.utils.power_tools_library.start_gin_server")
def test_start_gin_success(mock_start, library):
    library._projects["api"] = ManagedProject(
        info=ProjectInfo(name="api", framework=FrameworkType.GIN, path="/tmp/api"),
    )
    mock_start.return_value = {"success": True, "pid": 5678, "port": 9090}

    result = library.start_gin("api", requester="web_architect", port=9090)
    assert result["success"]
    assert library._projects["api"].info.pid == 5678
    assert library._projects["api"].info.running
    assert library._projects["api"].last_action_by == "web_architect"


def test_start_gin_unknown_project(library):
    result = library.start_gin("nonexistent")
    assert not result["success"]


def test_start_gin_wrong_framework(library):
    library._projects["rails_app"] = ManagedProject(
        info=ProjectInfo(name="rails_app", framework=FrameworkType.RAILS, path="/tmp/r"),
    )
    result = library.start_gin("rails_app")
    assert not result["success"]
    assert "not a Gin" in result["error"]


# ---------------------------------------------------------------
# Project management
# ---------------------------------------------------------------

def test_tag_project(library):
    library._projects["app"] = ManagedProject(
        info=ProjectInfo(name="app", framework=FrameworkType.RAILS, path="/tmp/app"),
        tags=["rails"],
    )
    assert library.tag_project("app", ["production", "v2"])
    assert "production" in library._projects["app"].tags
    assert "v2" in library._projects["app"].tags
    assert "rails" in library._projects["app"].tags  # existing preserved


def test_tag_nonexistent_project(library):
    assert not library.tag_project("nonexistent", ["test"])


def test_remove_project(library):
    library._projects["old_app"] = ManagedProject(
        info=ProjectInfo(name="old_app", framework=FrameworkType.GIN, path="/tmp/old"),
    )
    assert library.remove_project("old_app")
    assert "old_app" not in library._projects


def test_remove_nonexistent_project(library):
    assert not library.remove_project("nonexistent")


# ---------------------------------------------------------------
# Summary text
# ---------------------------------------------------------------

@patch("guardian_one.utils.power_tools_library.power_tools_status")
def test_summary_text_with_projects(mock_status, library):
    mock_status.return_value = {
        "ruby": {"status": "installed", "version": "ruby 3.3"},
        "rails": {"status": "installed", "version": "Rails 7.1"},
        "go": {"status": "installed", "version": "go1.22"},
        "gin": {"status": "installed", "note": "per-project"},
    }
    library._projects["myapp"] = ManagedProject(
        info=ProjectInfo(name="myapp", framework=FrameworkType.RAILS, path="/tmp/myapp", port=3000),
        tags=["rails", "web"],
    )
    text = library.summary_text()
    assert "POWER TOOLS LIBRARY" in text
    assert "myapp" in text
    assert "RAILS" in text
    assert "MANAGED PROJECTS (1)" in text


@patch("guardian_one.utils.power_tools_library.power_tools_status")
def test_summary_text_empty(mock_status, library):
    mock_status.return_value = {
        "ruby": {"status": "not_installed", "version": ""},
        "rails": {"status": "not_installed", "version": ""},
        "go": {"status": "not_installed", "version": ""},
        "gin": {"status": "not_installed", "note": ""},
    }
    text = library.summary_text()
    assert "No managed projects" in text


# ---------------------------------------------------------------
# Archivist integration
# ---------------------------------------------------------------

def test_archivist_power_tools_attachment(audit):
    from guardian_one.core.config import AgentConfig
    from guardian_one.agents.archivist import Archivist

    cfg = AgentConfig(name="archivist", allowed_resources=["power_tools"])
    archivist = Archivist(config=cfg, audit=audit)
    archivist.initialize()

    assert archivist.power_tools is None  # Not yet injected

    with tempfile.TemporaryDirectory() as data_dir:
        lib = PowerToolsLibrary(audit=audit, data_dir=data_dir)
        archivist.set_power_tools(lib)

        assert archivist.power_tools is lib
        status = archivist.power_tools_status()
        assert "managed_projects" in status


def test_archivist_report_includes_power_tools(audit):
    from guardian_one.core.config import AgentConfig
    from guardian_one.agents.archivist import Archivist

    cfg = AgentConfig(name="archivist", allowed_resources=["power_tools"])
    archivist = Archivist(config=cfg, audit=audit)
    archivist.initialize()

    with tempfile.TemporaryDirectory() as data_dir:
        lib = PowerToolsLibrary(audit=audit, data_dir=data_dir)
        archivist.set_power_tools(lib)

        report = archivist.report()
        assert "power tool project(s)" in report.summary
        assert report.data["power_tools_projects"] == 0


def test_archivist_run_includes_power_tools(audit):
    from guardian_one.core.config import AgentConfig
    from guardian_one.agents.archivist import Archivist

    cfg = AgentConfig(name="archivist", allowed_resources=["power_tools"])
    archivist = Archivist(config=cfg, audit=audit)
    archivist.initialize()

    with tempfile.TemporaryDirectory() as data_dir:
        lib = PowerToolsLibrary(audit=audit, data_dir=data_dir)
        archivist.set_power_tools(lib)

        report = archivist.run()
        assert "power tool project(s)" in report.summary
        assert "Power tools library" in report.actions_taken[-1]


def test_archivist_without_power_tools(audit):
    """Archivist still works fine without power tools attached."""
    from guardian_one.core.config import AgentConfig
    from guardian_one.agents.archivist import Archivist

    cfg = AgentConfig(name="archivist")
    archivist = Archivist(config=cfg, audit=audit)
    archivist.initialize()

    report = archivist.run()
    assert report.status == "idle"

    status = archivist.power_tools_status()
    assert "error" in status


# ---------------------------------------------------------------
# Web Architect integration
# ---------------------------------------------------------------

def test_web_architect_power_tools_methods(audit):
    from guardian_one.core.config import AgentConfig
    from guardian_one.agents.web_architect import WebArchitect

    cfg = AgentConfig(name="web_architect", allowed_resources=["power_tools"])
    wa = WebArchitect(config=cfg, audit=audit)

    # Without library
    result = wa.scaffold_rails_site("test_app")
    assert not result["success"]
    assert "not available" in result["error"]

    result = wa.scaffold_gin_api("test_api")
    assert not result["success"]
    assert "not available" in result["error"]


@patch("guardian_one.utils.power_tools_library.scaffold_rails")
def test_web_architect_scaffold_rails_via_library(mock_scaffold, audit):
    from guardian_one.core.config import AgentConfig
    from guardian_one.agents.web_architect import WebArchitect

    mock_scaffold.return_value = {
        "success": True,
        "path": "/tmp/site",
        "project": ProjectInfo(name="site", framework=FrameworkType.RAILS, path="/tmp/site", port=3000),
    }

    cfg = AgentConfig(name="web_architect", allowed_resources=["power_tools"])
    wa = WebArchitect(config=cfg, audit=audit)

    with tempfile.TemporaryDirectory() as data_dir:
        lib = PowerToolsLibrary(audit=audit, data_dir=data_dir)
        wa.set_power_tools(lib)

        result = wa.scaffold_rails_site("site")
        assert result["success"]
        assert "site" in lib._projects
        assert "web_architect" in lib._projects["site"].tags


@patch("guardian_one.utils.power_tools_library.scaffold_gin")
def test_web_architect_scaffold_gin_via_library(mock_scaffold, audit):
    from guardian_one.core.config import AgentConfig
    from guardian_one.agents.web_architect import WebArchitect

    mock_scaffold.return_value = {
        "success": True,
        "path": "/tmp/api",
        "project": ProjectInfo(name="api", framework=FrameworkType.GIN, path="/tmp/api", port=8080),
    }

    cfg = AgentConfig(name="web_architect", allowed_resources=["power_tools"])
    wa = WebArchitect(config=cfg, audit=audit)

    with tempfile.TemporaryDirectory() as data_dir:
        lib = PowerToolsLibrary(audit=audit, data_dir=data_dir)
        wa.set_power_tools(lib)

        result = wa.scaffold_gin_api("api")
        assert result["success"]
        assert "api" in lib._projects
        assert "web_architect" in lib._projects["api"].tags
