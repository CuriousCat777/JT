"""Tests for PasswordSync — 1Password / Bitwarden CLI integration."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from guardian_one.archivist.password_sync import PasswordSync, VaultItem


class TestPasswordSync:
    @pytest.fixture
    def sync(self, tmp_path):
        return PasswordSync(backend="1password", data_dir=tmp_path)

    def test_check_cli_missing(self, sync):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert sync.check_cli() is False

    def test_check_cli_available(self, sync):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            assert sync.check_cli() is True

    def test_sync_no_cli(self, sync):
        sync._cli_available = False
        result = sync.sync()
        assert result["success"] is False
        assert "not available" in result["error"]

    def test_sync_1password(self, sync):
        sync._cli_available = True
        fake_items = [
            {
                "title": "GitHub",
                "vault": {"name": "Personal"},
                "category": "LOGIN",
                "urls": [{"href": "https://github.com"}],
                "updated_at": "2025-01-01T00:00:00Z",
                "tags": ["dev"],
            },
            {
                "title": "Gmail",
                "vault": {"name": "Personal"},
                "category": "LOGIN",
                "urls": [{"href": "https://mail.google.com"}],
                "updated_at": "2025-02-01T00:00:00Z",
                "tags": [],
            },
        ]
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(fake_items)
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = sync.sync()

        assert result["success"] is True
        assert result["items_synced"] == 2
        assert len(sync.items) == 2
        assert sync.items[0].name == "GitHub"
        assert sync.items[0].url == "https://github.com"

    def test_sync_bitwarden(self, tmp_path):
        sync = PasswordSync(backend="bitwarden", data_dir=tmp_path)
        sync._cli_available = True
        fake_items = [
            {
                "name": "GitHub",
                "type": 1,
                "login": {
                    "username": "curiouscat777",
                    "uris": [{"uri": "https://github.com"}],
                    "totp": "otpauth://...",
                },
                "revisionDate": "2025-01-15T00:00:00Z",
            },
        ]
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(fake_items)
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = sync.sync()

        assert result["success"] is True
        assert sync.items[0].username == "curiouscat777"
        assert sync.items[0].has_totp is True


class TestAudit:
    def test_audit_empty(self, tmp_path):
        sync = PasswordSync(data_dir=tmp_path)
        result = sync.audit()
        assert "error" in result

    def test_audit_with_items(self, tmp_path):
        sync = PasswordSync(data_dir=tmp_path)
        sync._items = [
            VaultItem(name="Secure", category="login", has_totp=True, password_strength="strong"),
            VaultItem(name="Weak", category="login", has_totp=False, password_strength="weak"),
            VaultItem(name="Compromised", category="login", compromised=True),
        ]
        result = sync.audit()
        assert result["logins"] == 3
        assert "Weak" in result["weak_passwords"]
        assert "Weak" in result["missing_2fa"]
        assert "Compromised" in result["compromised"]
        assert 0 <= result["score"] <= 100


class TestPersistence:
    def test_cache_round_trip(self, tmp_path):
        s1 = PasswordSync(data_dir=tmp_path)
        s1._items = [
            VaultItem(name="GitHub", category="login", url="https://github.com"),
            VaultItem(name="Gmail", category="login", url="https://gmail.com"),
        ]
        s1._last_sync = "2025-01-01T00:00:00Z"
        s1._save_cache()

        s2 = PasswordSync(data_dir=tmp_path)
        s2.load_cache()
        assert len(s2.items) == 2
        assert s2.items[0].name == "GitHub"
        assert s2.last_sync == "2025-01-01T00:00:00Z"


class TestStatus:
    def test_status(self, tmp_path):
        sync = PasswordSync(backend="bitwarden", data_dir=tmp_path)
        status = sync.status()
        assert status["backend"] == "bitwarden"
        assert status["items_cached"] == 0
