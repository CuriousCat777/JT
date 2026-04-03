"""Tests for Rails + Gin power tools integration.

All tests use mocks — no actual Ruby, Rails, Go, or Gin required.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch, call
import tempfile

import pytest

from guardian_one.integrations.rails_gin import (
    FrameworkInfo,
    FrameworkType,
    ProjectInfo,
    ToolStatus,
    _run_cmd,
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


# ---------------------------------------------------------------
# _run_cmd
# ---------------------------------------------------------------

@patch("guardian_one.integrations.rails_gin.subprocess.run")
def test_run_cmd_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
    rc, out, err = _run_cmd(["echo", "hi"])
    assert rc == 0
    assert out == "ok"


@patch("guardian_one.integrations.rails_gin.subprocess.run")
def test_run_cmd_not_found(mock_run):
    mock_run.side_effect = FileNotFoundError()
    rc, out, err = _run_cmd(["nonexistent"])
    assert rc == -1
    assert "command not found" in err


@patch("guardian_one.integrations.rails_gin.subprocess.run")
def test_run_cmd_timeout(mock_run):
    import subprocess
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)
    rc, out, err = _run_cmd(["slow"], timeout=5)
    assert rc == -2
    assert "timed out" in err


# ---------------------------------------------------------------
# check_ruby / check_rails / check_go / check_gin
# ---------------------------------------------------------------

@patch("guardian_one.integrations.rails_gin._run_cmd")
@patch("guardian_one.integrations.rails_gin.shutil.which", return_value="/usr/bin/ruby")
def test_check_ruby_installed(mock_which, mock_cmd):
    mock_cmd.return_value = (0, "ruby 3.3.0", "")
    info = check_ruby()
    assert info.status == ToolStatus.INSTALLED
    assert "3.3.0" in info.version
    assert info.path == "/usr/bin/ruby"


@patch("guardian_one.integrations.rails_gin._run_cmd")
def test_check_ruby_not_installed(mock_cmd):
    mock_cmd.return_value = (-1, "", "command not found: ruby")
    info = check_ruby()
    assert info.status == ToolStatus.NOT_INSTALLED


@patch("guardian_one.integrations.rails_gin._run_cmd")
@patch("guardian_one.integrations.rails_gin.shutil.which", return_value="/usr/local/bin/rails")
def test_check_rails_installed(mock_which, mock_cmd):
    mock_cmd.return_value = (0, "Rails 7.1.3", "")
    info = check_rails()
    assert info.status == ToolStatus.INSTALLED
    assert "7.1" in info.version


@patch("guardian_one.integrations.rails_gin._run_cmd")
def test_check_rails_not_installed(mock_cmd):
    mock_cmd.return_value = (-1, "", "command not found: rails")
    info = check_rails()
    assert info.status == ToolStatus.NOT_INSTALLED


@patch("guardian_one.integrations.rails_gin._run_cmd")
@patch("guardian_one.integrations.rails_gin.shutil.which", return_value="/usr/local/go/bin/go")
def test_check_go_installed(mock_which, mock_cmd):
    mock_cmd.return_value = (0, "go version go1.22.0 linux/amd64", "")
    info = check_go()
    assert info.status == ToolStatus.INSTALLED
    assert "1.22" in info.version


@patch("guardian_one.integrations.rails_gin._run_cmd")
def test_check_go_not_installed(mock_cmd):
    mock_cmd.return_value = (-1, "", "command not found: go")
    info = check_go()
    assert info.status == ToolStatus.NOT_INSTALLED


@patch("guardian_one.integrations.rails_gin.check_go")
def test_check_gin_requires_go(mock_go):
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.NOT_INSTALLED,
        details={"error": "Go is not installed"},
    )
    info = check_gin()
    assert info.status == ToolStatus.NOT_INSTALLED
    assert "Go" in info.details["error"]


@patch("guardian_one.integrations.rails_gin.check_go")
def test_check_gin_available(mock_go):
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.INSTALLED,
        version="go version go1.22.0",
        path="/usr/local/go/bin/go",
    )
    info = check_gin()
    assert info.status == ToolStatus.INSTALLED
    assert "per-project" in info.details.get("note", "")


# ---------------------------------------------------------------
# install_rails
# ---------------------------------------------------------------

@patch("guardian_one.integrations.rails_gin.check_rails")
@patch("guardian_one.integrations.rails_gin.check_ruby")
def test_install_rails_no_ruby(mock_ruby, mock_rails):
    mock_ruby.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.NOT_INSTALLED,
    )
    result = install_rails()
    assert not result["success"]
    assert "Ruby" in result["error"]


@patch("guardian_one.integrations.rails_gin.check_rails")
@patch("guardian_one.integrations.rails_gin.check_ruby")
def test_install_rails_already_installed(mock_ruby, mock_rails):
    mock_ruby.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.INSTALLED,
        version="ruby 3.3.0",
    )
    mock_rails.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.INSTALLED,
        version="Rails 7.1.3",
    )
    result = install_rails()
    assert result["success"]
    assert result["already_installed"]


@patch("guardian_one.integrations.rails_gin._run_cmd")
@patch("guardian_one.integrations.rails_gin.check_rails")
@patch("guardian_one.integrations.rails_gin.check_ruby")
def test_install_rails_fresh(mock_ruby, mock_rails_before, mock_cmd):
    mock_ruby.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.INSTALLED,
        version="ruby 3.3.0",
    )
    mock_rails_before.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.NOT_INSTALLED,
    )
    # gem install succeeds, then check_rails succeeds
    mock_cmd.return_value = (0, "Successfully installed rails-7.1.3", "")
    with patch("guardian_one.integrations.rails_gin.check_rails") as mock_rails_after:
        mock_rails_after.return_value = FrameworkInfo(
            framework=FrameworkType.RAILS,
            status=ToolStatus.INSTALLED,
            version="Rails 7.1.3",
        )
        result = install_rails()
    assert result["success"]


# ---------------------------------------------------------------
# install_gin
# ---------------------------------------------------------------

@patch("guardian_one.integrations.rails_gin.check_go")
def test_install_gin_no_go(mock_go):
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.NOT_INSTALLED,
    )
    result = install_gin("/some/path")
    assert not result["success"]
    assert "Go" in result["error"]


@patch("guardian_one.integrations.rails_gin.check_go")
def test_install_gin_no_gomod(mock_go):
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.INSTALLED,
        version="go1.22.0",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        result = install_gin(tmpdir)
        assert not result["success"]
        assert "go.mod" in result["error"]


@patch("guardian_one.integrations.rails_gin._run_cmd")
@patch("guardian_one.integrations.rails_gin.check_go")
def test_install_gin_success(mock_go, mock_cmd):
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.INSTALLED,
        version="go1.22.0",
    )
    mock_cmd.return_value = (0, "go: added github.com/gin-gonic/gin", "")
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "go.mod").touch()
        result = install_gin(tmpdir)
        assert result["success"]


# ---------------------------------------------------------------
# scaffold_rails
# ---------------------------------------------------------------

@patch("guardian_one.integrations.rails_gin.check_rails")
def test_scaffold_rails_not_installed(mock_rails):
    mock_rails.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.NOT_INSTALLED,
    )
    result = scaffold_rails("myapp")
    assert not result["success"]
    assert "not installed" in result["error"]


@patch("guardian_one.integrations.rails_gin.check_rails")
def test_scaffold_rails_dir_exists(mock_rails):
    mock_rails.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.INSTALLED,
        version="Rails 7.1.3",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        existing = Path(tmpdir) / "myapp"
        existing.mkdir()
        result = scaffold_rails("myapp", parent_dir=tmpdir)
        assert not result["success"]
        assert "already exists" in result["error"]


@patch("guardian_one.integrations.rails_gin._run_cmd")
@patch("guardian_one.integrations.rails_gin.check_rails")
def test_scaffold_rails_success(mock_rails, mock_cmd):
    mock_rails.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.INSTALLED,
        version="Rails 7.1.3",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "myapp"

        def fake_run(cmd, timeout=30):
            # Simulate rails new creating the directory
            target.mkdir(parents=True, exist_ok=True)
            return (0, "Rails app created", "")

        mock_cmd.side_effect = fake_run
        result = scaffold_rails("myapp", parent_dir=tmpdir)
        assert result["success"]
        assert result["path"] == str(target)
        assert result["project"].framework == FrameworkType.RAILS
        assert result["project"].port == 3000


@patch("guardian_one.integrations.rails_gin._run_cmd")
@patch("guardian_one.integrations.rails_gin.check_rails")
def test_scaffold_rails_api_only(mock_rails, mock_cmd):
    mock_rails.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.INSTALLED,
        version="Rails 7.1.3",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "api_app"

        def fake_run(cmd, timeout=30):
            assert "--api" in cmd
            target.mkdir(parents=True, exist_ok=True)
            return (0, "API app created", "")

        mock_cmd.side_effect = fake_run
        result = scaffold_rails("api_app", parent_dir=tmpdir, api_only=True)
        assert result["success"]


# ---------------------------------------------------------------
# scaffold_gin
# ---------------------------------------------------------------

@patch("guardian_one.integrations.rails_gin.check_go")
def test_scaffold_gin_no_go(mock_go):
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.NOT_INSTALLED,
    )
    result = scaffold_gin("myapi")
    assert not result["success"]
    assert "Go" in result["error"]


@patch("guardian_one.integrations.rails_gin.check_go")
def test_scaffold_gin_dir_exists(mock_go):
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.INSTALLED,
        version="go1.22.0",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        existing = Path(tmpdir) / "myapi"
        existing.mkdir()
        result = scaffold_gin("myapi", parent_dir=tmpdir)
        assert not result["success"]
        assert "already exists" in result["error"]


@patch("guardian_one.integrations.rails_gin.install_gin")
@patch("guardian_one.integrations.rails_gin._run_cmd")
@patch("guardian_one.integrations.rails_gin.check_go")
def test_scaffold_gin_success(mock_go, mock_cmd, mock_install):
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.INSTALLED,
        version="go1.22.0",
    )
    mock_cmd.return_value = (0, "", "")  # go mod init + go mod tidy
    mock_install.return_value = {"success": True, "output": "gin installed"}

    with tempfile.TemporaryDirectory() as tmpdir:
        result = scaffold_gin("myapi", parent_dir=tmpdir, port=9090)
        assert result["success"]
        target = Path(tmpdir) / "myapi"
        assert (target / "main.go").exists()
        assert (target / "routes" / "api.go").exists()
        assert (target / "middleware" / "cors.go").exists()

        # Check main.go content
        main_content = (target / "main.go").read_text()
        assert "gin.Default()" in main_content
        assert "9090" in main_content
        assert "/health" in main_content

        # Check routes
        routes_content = (target / "routes" / "api.go").read_text()
        assert "/api/v1" in routes_content
        assert "/ping" in routes_content

        # Check middleware
        cors_content = (target / "middleware" / "cors.go").read_text()
        assert "Access-Control-Allow-Origin" in cors_content

        # Check project info
        assert result["project"].framework == FrameworkType.GIN
        assert result["project"].port == 9090


@patch("guardian_one.integrations.rails_gin.install_gin")
@patch("guardian_one.integrations.rails_gin._run_cmd")
@patch("guardian_one.integrations.rails_gin.check_go")
def test_scaffold_gin_install_fails(mock_go, mock_cmd, mock_install):
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN,
        status=ToolStatus.INSTALLED,
        version="go1.22.0",
    )
    mock_cmd.return_value = (0, "", "")
    mock_install.return_value = {"success": False, "error": "network timeout"}

    with tempfile.TemporaryDirectory() as tmpdir:
        result = scaffold_gin("myapi", parent_dir=tmpdir)
        assert not result["success"]
        assert "network timeout" in result["error"]


# ---------------------------------------------------------------
# start_rails_server / start_gin_server
# ---------------------------------------------------------------

def test_start_rails_server_not_rails_app():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = start_rails_server(tmpdir)
        assert not result["success"]
        assert "Not a Rails app" in result["error"]


@patch("guardian_one.integrations.rails_gin.subprocess.Popen")
def test_start_rails_server_success(mock_popen):
    mock_popen.return_value = MagicMock(pid=12345)
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "Gemfile").touch()
        result = start_rails_server(tmpdir, port=3001)
        assert result["success"]
        assert result["pid"] == 12345
        assert result["port"] == 3001
        assert "3001" in result["url"]


def test_start_gin_server_no_main_go():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = start_gin_server(tmpdir)
        assert not result["success"]
        assert "No main.go" in result["error"]


@patch("guardian_one.integrations.rails_gin.subprocess.Popen")
def test_start_gin_server_success(mock_popen):
    mock_popen.return_value = MagicMock(pid=54321)
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "main.go").touch()
        result = start_gin_server(tmpdir, port=9090)
        assert result["success"]
        assert result["pid"] == 54321
        assert result["port"] == 9090
        assert "9090" in result["url"]


# ---------------------------------------------------------------
# power_tools_status
# ---------------------------------------------------------------

@patch("guardian_one.integrations.rails_gin.check_gin")
@patch("guardian_one.integrations.rails_gin.check_go")
@patch("guardian_one.integrations.rails_gin.check_rails")
@patch("guardian_one.integrations.rails_gin.check_ruby")
def test_power_tools_status(mock_ruby, mock_rails, mock_go, mock_gin):
    mock_ruby.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS, status=ToolStatus.INSTALLED,
        version="ruby 3.3.0", path="/usr/bin/ruby",
    )
    mock_rails.return_value = FrameworkInfo(
        framework=FrameworkType.RAILS, status=ToolStatus.INSTALLED,
        version="Rails 7.1.3", path="/usr/local/bin/rails",
    )
    mock_go.return_value = FrameworkInfo(
        framework=FrameworkType.GIN, status=ToolStatus.INSTALLED,
        version="go1.22.0", path="/usr/local/go/bin/go",
    )
    mock_gin.return_value = FrameworkInfo(
        framework=FrameworkType.GIN, status=ToolStatus.INSTALLED,
        version="go1.22.0",
        details={"note": "Gin installs per-project via go module"},
    )

    status = power_tools_status()

    assert status["ruby"]["status"] == "installed"
    assert status["rails"]["status"] == "installed"
    assert status["go"]["status"] == "installed"
    assert status["gin"]["status"] == "installed"
    assert "capabilities" in status
    assert "rails" in status["capabilities"]
    assert "gin" in status["capabilities"]
    assert "use_cases" in status
    assert "rails_frontend_gin_api" in status["use_cases"]
    assert "gin_microservice" in status["use_cases"]
    assert "guardian_one_api" in status["use_cases"]
    assert "timestamp" in status


@patch("guardian_one.integrations.rails_gin.check_gin")
@patch("guardian_one.integrations.rails_gin.check_go")
@patch("guardian_one.integrations.rails_gin.check_rails")
@patch("guardian_one.integrations.rails_gin.check_ruby")
def test_power_tools_status_nothing_installed(mock_ruby, mock_rails, mock_go, mock_gin):
    for mock in (mock_ruby, mock_rails, mock_go, mock_gin):
        mock.return_value = FrameworkInfo(
            framework=FrameworkType.RAILS, status=ToolStatus.NOT_INSTALLED,
        )

    status = power_tools_status()
    assert status["ruby"]["status"] == "not_installed"
    assert status["rails"]["status"] == "not_installed"
    assert status["go"]["status"] == "not_installed"
    assert status["gin"]["status"] == "not_installed"


# ---------------------------------------------------------------
# ProjectInfo
# ---------------------------------------------------------------

def test_project_info_defaults():
    proj = ProjectInfo(
        name="test_app",
        framework=FrameworkType.RAILS,
        path="/tmp/test_app",
    )
    assert proj.name == "test_app"
    assert proj.framework == FrameworkType.RAILS
    assert proj.pid is None
    assert not proj.running
    assert proj.created_at  # auto-set


def test_project_info_gin():
    proj = ProjectInfo(
        name="api_server",
        framework=FrameworkType.GIN,
        path="/tmp/api_server",
        port=8080,
    )
    assert proj.framework == FrameworkType.GIN
    assert proj.port == 8080


# ---------------------------------------------------------------
# FrameworkInfo
# ---------------------------------------------------------------

def test_framework_info_defaults():
    info = FrameworkInfo(
        framework=FrameworkType.RAILS,
        status=ToolStatus.NOT_INSTALLED,
    )
    assert info.version == ""
    assert info.path == ""
    assert info.details == {}
