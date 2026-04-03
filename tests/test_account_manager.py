"""Tests for AccountManager — unified account/storage tracker."""

from pathlib import Path

import pytest

from guardian_one.archivist.account_manager import AccountManager, AccountRecord


class TestAccountManager:
    @pytest.fixture
    def mgr(self, tmp_path):
        return AccountManager(data_dir=tmp_path)

    def test_add_and_get(self, mgr):
        mgr.add(AccountRecord(
            name="Gmail", provider="google", account_type="email",
            email="jeremy@gmail.com",
        ))
        account = mgr.get("google", "Gmail")
        assert account is not None
        assert account.email == "jeremy@gmail.com"

    def test_remove(self, mgr):
        mgr.add(AccountRecord(name="Test", provider="test"))
        assert mgr.remove("test", "Test") is True
        assert mgr.get("test", "Test") is None

    def test_search_by_type(self, mgr):
        mgr.add(AccountRecord(name="Gmail", provider="google", account_type="email"))
        mgr.add(AccountRecord(name="GitHub", provider="github", account_type="developer"))
        mgr.add(AccountRecord(name="Outlook", provider="microsoft", account_type="email"))

        emails = mgr.search(account_type="email")
        assert len(emails) == 2

    def test_search_by_provider(self, mgr):
        mgr.add(AccountRecord(name="Gmail", provider="google", account_type="email"))
        mgr.add(AccountRecord(name="Drive", provider="google", account_type="cloud_storage"))

        google = mgr.search(provider="google")
        assert len(google) == 2

    def test_search_active_only(self, mgr):
        mgr.add(AccountRecord(name="Active", provider="test", active=True))
        mgr.add(AccountRecord(name="Inactive", provider="test", active=False))

        active = mgr.search(active_only=True)
        assert len(active) == 1
        assert active[0].name == "Active"


class TestPasswordHealth:
    @pytest.fixture
    def mgr(self, tmp_path):
        m = AccountManager(data_dir=tmp_path)
        m.add(AccountRecord(
            name="Gmail", provider="google", account_type="email",
            has_2fa=True, password_strength="strong",
            password_manager="1password", password_age_days=30,
        ))
        m.add(AccountRecord(
            name="OldSite", provider="oldsite", account_type="social",
            has_2fa=False, password_strength="weak",
            password_manager="none", password_age_days=200,
        ))
        return m

    def test_password_health(self, mgr):
        health = mgr.password_health()
        assert health["total_accounts"] == 2
        assert "OldSite" in health["weak_passwords"]
        assert "OldSite" in health["missing_2fa"]
        assert "OldSite" in health["old_passwords_90d"]
        assert "OldSite" in health["not_in_password_manager"]

    def test_health_score_perfect(self, tmp_path):
        mgr = AccountManager(data_dir=tmp_path)
        mgr.add(AccountRecord(
            name="Secure", provider="test",
            has_2fa=True, password_strength="strong",
            password_manager="1password", password_age_days=10,
        ))
        health = mgr.password_health()
        assert health["score"] == 100

    def test_health_score_empty(self, tmp_path):
        mgr = AccountManager(data_dir=tmp_path)
        assert mgr.password_health()["score"] == 100


class TestStorageSummary:
    def test_storage_summary(self, tmp_path):
        mgr = AccountManager(data_dir=tmp_path)
        mgr.add(AccountRecord(
            name="Google Drive", provider="google",
            account_type="cloud_storage",
            storage_used_mb=10_000, storage_quota_mb=15_000,
        ))
        mgr.add(AccountRecord(
            name="iCloud", provider="apple",
            account_type="cloud_storage",
            storage_used_mb=180_000, storage_quota_mb=200_000,
        ))

        summary = mgr.storage_summary()
        assert summary["accounts_with_storage"] == 2
        assert summary["total_used_gb"] > 0
        assert len(summary["over_80_pct"]) == 1  # iCloud at 90%

    def test_storage_usage_pct(self):
        a = AccountRecord(name="Test", provider="test",
                         storage_used_mb=80, storage_quota_mb=100)
        assert a.storage_usage_pct == 80.0


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        m1 = AccountManager(data_dir=tmp_path)
        m1.add(AccountRecord(
            name="GitHub", provider="github",
            account_type="developer", username="curiouscat777",
        ))
        m1.save()

        m2 = AccountManager(data_dir=tmp_path)
        m2.load()
        account = m2.get("github", "GitHub")
        assert account is not None
        assert account.username == "curiouscat777"


class TestStatus:
    def test_status(self, tmp_path):
        mgr = AccountManager(data_dir=tmp_path)
        mgr.add(AccountRecord(name="A", provider="p", account_type="email"))
        mgr.add(AccountRecord(name="B", provider="p", account_type="developer"))
        status = mgr.status()
        assert status["total_accounts"] == 2
        assert status["by_type"]["email"] == 1
