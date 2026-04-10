"""Tests for GOOS — Guardian One Operating System platform layer."""

from __future__ import annotations

import pytest

from guardian_one.goos.client import (
    ClientRegistry,
    ClientStatus,
    ClientTier,
    GOOSClient,
    OnboardingStep,
    VarysNode,
)
from guardian_one.goos.registration import RegistrationService
from guardian_one.goos.onboarding import OnboardingEngine
from guardian_one.goos.api import GOOSAPI


# ---------------------------------------------------------------------------
# Client model tests
# ---------------------------------------------------------------------------

class TestGOOSClient:
    def test_default_agents_free(self):
        client = GOOSClient(
            client_id="test", email="a@b.com", display_name="Test",
            tier=ClientTier.FREE,
        )
        agents = client.default_agents_for_tier()
        assert "guardian" in agents
        assert "varys" in agents
        assert "cfo" not in agents

    def test_default_agents_premium(self):
        client = GOOSClient(
            client_id="test", email="a@b.com", display_name="Test",
            tier=ClientTier.PREMIUM,
        )
        agents = client.default_agents_for_tier()
        assert "cfo" in agents
        assert "chronos" in agents

    def test_default_agents_sovereign(self):
        client = GOOSClient(
            client_id="test", email="a@b.com", display_name="Test",
            tier=ClientTier.SOVEREIGN,
        )
        agents = client.default_agents_for_tier()
        assert "dev_coach" in agents
        assert "web_architect" in agents

    def test_to_dict(self):
        client = GOOSClient(
            client_id="abc", email="j@t.com", display_name="Jeremy",
        )
        d = client.to_dict()
        assert d["client_id"] == "abc"
        assert d["email"] == "j@t.com"
        assert d["tier"] == "free"
        assert d["status"] == "pending"

    def test_is_verified(self):
        client = GOOSClient(
            client_id="x", email="a@b.com", display_name="Test",
        )
        assert not client.is_verified
        client.verified_at = "2026-01-01T00:00:00Z"
        assert client.is_verified

    def test_has_varys_empty(self):
        client = GOOSClient(
            client_id="x", email="a@b.com", display_name="Test",
        )
        assert not client.has_varys


# ---------------------------------------------------------------------------
# Client registry tests
# ---------------------------------------------------------------------------

class TestClientRegistry:
    def test_create_client(self):
        reg = ClientRegistry()
        client = reg.create_client("test@example.com", "Test User")
        assert client.client_id
        assert client.email == "test@example.com"
        assert client.status == ClientStatus.PENDING

    def test_duplicate_email(self):
        reg = ClientRegistry()
        reg.create_client("test@example.com", "User 1")
        with pytest.raises(ValueError, match="already exists"):
            reg.create_client("test@example.com", "User 2")

    def test_email_case_insensitive(self):
        reg = ClientRegistry()
        reg.create_client("Test@Example.COM", "User")
        with pytest.raises(ValueError):
            reg.create_client("test@example.com", "User 2")

    def test_verify_email(self):
        reg = ClientRegistry()
        client = reg.create_client("a@b.com", "Test")
        token = client.verification_token
        assert reg.verify_email(client.client_id, token)
        updated = reg.get_client(client.client_id)
        assert updated.status == ClientStatus.ONBOARDING
        assert updated.is_verified

    def test_verify_wrong_token(self):
        reg = ClientRegistry()
        client = reg.create_client("a@b.com", "Test")
        assert not reg.verify_email(client.client_id, "wrong-token")

    def test_advance_onboarding(self):
        reg = ClientRegistry()
        client = reg.create_client("a@b.com", "Test")
        reg.verify_email(client.client_id, client.verification_token)

        # Should be at MEET_GUARDIAN after verification
        assert client.onboarding_step == OnboardingStep.MEET_GUARDIAN

        # Advance through steps
        next_step = reg.advance_onboarding(client.client_id)
        assert next_step == OnboardingStep.FILE_EXCHANGE

    def test_full_onboarding_completes(self):
        reg = ClientRegistry()
        client = reg.create_client("a@b.com", "Test")
        reg.verify_email(client.client_id, client.verification_token)

        # Advance through all steps
        steps = list(OnboardingStep)
        current_idx = steps.index(client.onboarding_step)
        for _ in range(len(steps) - current_idx - 1):
            reg.advance_onboarding(client.client_id)

        assert client.onboarding_step == OnboardingStep.COMPLETE
        assert client.status == ClientStatus.ACTIVE

    def test_register_varys_node(self):
        reg = ClientRegistry()
        client = reg.create_client("a@b.com", "Test")
        node = reg.register_varys_node(client.client_id, "my-laptop", "linux")
        assert node is not None
        assert node.hostname == "my-laptop"
        assert client.has_varys

    def test_offline_mode(self):
        reg = ClientRegistry()
        client = reg.create_client("a@b.com", "Test")
        assert reg.set_offline_mode(client.client_id)
        assert client.status == ClientStatus.OFFLINE

    def test_reconnect(self):
        reg = ClientRegistry()
        client = reg.create_client("a@b.com", "Test")
        reg.set_offline_mode(client.client_id)
        assert reg.reconnect(client.client_id)
        assert client.status == ClientStatus.ACTIVE

    def test_get_by_email(self):
        reg = ClientRegistry()
        client = reg.create_client("test@mail.com", "Test")
        found = reg.get_by_email("test@mail.com")
        assert found is not None
        assert found.client_id == client.client_id

    def test_list_clients(self):
        reg = ClientRegistry()
        reg.create_client("a@b.com", "A")
        reg.create_client("c@d.com", "C")
        assert reg.count == 2
        assert len(reg.list_clients()) == 2


# ---------------------------------------------------------------------------
# Registration service tests
# ---------------------------------------------------------------------------

class TestRegistrationService:
    def _make_service(self):
        reg = ClientRegistry()
        return RegistrationService(registry=reg), reg

    def test_register_success(self):
        svc, reg = self._make_service()
        result = svc.register(
            email="test@example.com",
            display_name="Test User",
            password="strongpassword123",
            captcha_token="valid",
        )
        assert result.success
        assert result.client_id

    def test_register_invalid_email(self):
        svc, _ = self._make_service()
        result = svc.register(
            email="not-an-email",
            display_name="Test",
            password="strongpassword123",
            captcha_token="valid",
        )
        assert not result.success
        assert "email" in result.error.lower()

    def test_register_short_password(self):
        svc, _ = self._make_service()
        result = svc.register(
            email="a@b.com",
            display_name="Test",
            password="short",
            captcha_token="valid",
        )
        assert not result.success
        assert "12 characters" in result.error

    def test_register_no_captcha(self):
        svc, _ = self._make_service()
        result = svc.register(
            email="a@b.com",
            display_name="Test",
            password="strongpassword123",
            captcha_token="",
        )
        assert not result.success
        assert "verification" in result.error.lower()

    def test_register_duplicate(self):
        svc, _ = self._make_service()
        svc.register("a@b.com", "Test", "strongpassword123", "valid")
        result = svc.register("a@b.com", "Test2", "strongpassword123", "valid")
        assert not result.success
        assert "already exists" in result.error

    def test_authenticate_success(self):
        svc, reg = self._make_service()
        result = svc.register("a@b.com", "Test", "mysecurepassword", "valid")
        # Verify email first
        client = reg.get_client(result.client_id)
        reg.verify_email(client.client_id, client.verification_token)

        auth = svc.authenticate("a@b.com", "mysecurepassword")
        assert auth.success
        assert auth.session_token

    def test_authenticate_wrong_password(self):
        svc, reg = self._make_service()
        result = svc.register("a@b.com", "Test", "mysecurepassword", "valid")
        client = reg.get_client(result.client_id)
        reg.verify_email(client.client_id, client.verification_token)

        auth = svc.authenticate("a@b.com", "wrongpassword")
        assert not auth.success

    def test_authenticate_unverified(self):
        svc, _ = self._make_service()
        svc.register("a@b.com", "Test", "mysecurepassword", "valid")
        auth = svc.authenticate("a@b.com", "mysecurepassword")
        assert not auth.success
        assert "not verified" in auth.error.lower()

    def test_password_hashing(self):
        hashed = RegistrationService._hash_password("testpass")
        assert ":" in hashed
        assert RegistrationService._verify_password("testpass", hashed)
        assert not RegistrationService._verify_password("wrong", hashed)


# ---------------------------------------------------------------------------
# Onboarding engine tests
# ---------------------------------------------------------------------------

class TestOnboardingEngine:
    def _setup(self):
        reg = ClientRegistry()
        engine = OnboardingEngine(registry=reg)
        client = reg.create_client("test@goos.com", "TestUser")
        reg.verify_email(client.client_id, client.verification_token)
        return engine, reg, client

    def test_welcome_step(self):
        reg = ClientRegistry()
        engine = OnboardingEngine(registry=reg)
        client = reg.create_client("a@b.com", "Test")
        # Before verification, client is at WELCOME
        msgs = engine.get_step_messages(client)
        assert len(msgs) >= 1
        assert "welcome" in msgs[0].step.lower()

    def test_meet_guardian_step(self):
        engine, reg, client = self._setup()
        msgs = engine.get_step_messages(client)
        assert any("Guardian" in m.content for m in msgs)

    def test_advance_through_onboarding(self):
        engine, reg, client = self._setup()

        # Advance from MEET_GUARDIAN → FILE_EXCHANGE
        msgs = engine.advance(client.client_id)
        assert client.onboarding_step == OnboardingStep.FILE_EXCHANGE

    def test_meet_cfo_messages(self):
        engine, reg, client = self._setup()

        # Advance to MEET_CFO
        while client.onboarding_step != OnboardingStep.MEET_CFO:
            engine.advance(client.client_id)

        msgs = engine.get_step_messages(client)
        assert any("CFO" in m.content for m in msgs)
        assert any(m.speaker == "cfo" for m in msgs)

    def test_meet_varys_messages(self):
        engine, reg, client = self._setup()

        # Advance to MEET_VARYS
        while client.onboarding_step != OnboardingStep.MEET_VARYS:
            engine.advance(client.client_id)

        msgs = engine.get_step_messages(client)
        assert any("Varys" in m.content for m in msgs)
        assert any(m.speaker == "varys" for m in msgs)

    def test_complete_messages(self):
        engine, reg, client = self._setup()

        # Advance to COMPLETE
        while client.onboarding_step != OnboardingStep.COMPLETE:
            engine.advance(client.client_id)

        msgs = engine.get_step_messages(client)
        assert any("onboarded" in m.content.lower() for m in msgs)

    def test_varys_node_registered_during_install(self):
        engine, reg, client = self._setup()

        # Advance to INSTALL_LOCAL
        while client.onboarding_step != OnboardingStep.INSTALL_LOCAL:
            engine.advance(client.client_id)

        # Advance with install data
        engine.advance(client.client_id, client_data={
            "hostname": "my-laptop",
            "os_type": "linux",
            "ip_local": "192.168.1.100",
        })

        assert len(client.varys_nodes) == 1
        assert client.varys_nodes[0].hostname == "my-laptop"


# ---------------------------------------------------------------------------
# GOOS API tests
# ---------------------------------------------------------------------------

class TestGOOSAPI:
    def test_register_and_login_flow(self):
        api = GOOSAPI()

        # Register
        result = api.register(
            email="test@goos.com",
            display_name="Test User",
            password="securepassword123",
            captcha_token="valid",
        )
        assert result["success"]
        client_id = result["client_id"]

        # Verify email
        client = api.registry.get_client(client_id)
        api.verify_email(client_id, client.verification_token)

        # Login
        auth = api.login("test@goos.com", "securepassword123")
        assert auth["success"]
        assert auth["session_token"]

    def test_onboarding_flow(self):
        api = GOOSAPI()

        # Register and verify
        result = api.register("a@b.com", "Test", "securepassword123", "valid")
        client_id = result["client_id"]
        client = api.registry.get_client(client_id)
        api.verify_email(client_id, client.verification_token)

        # Get onboarding step
        step_data = api.get_onboarding_step(client_id)
        assert step_data["step"] == "meet_guardian"
        assert len(step_data["messages"]) > 0

        # Advance
        advanced = api.advance_onboarding(client_id)
        assert advanced["step"] == "file_exchange"

    def test_register_varys_node(self):
        api = GOOSAPI()
        result = api.register("a@b.com", "Test", "securepassword123", "valid")
        client_id = result["client_id"]

        node = api.register_varys_node(client_id, "desktop", "linux")
        assert node["hostname"] == "desktop"

    def test_offline_reconnect(self):
        api = GOOSAPI()
        result = api.register("a@b.com", "Test", "securepassword123", "valid")
        client_id = result["client_id"]

        api.set_offline(client_id)
        client = api.registry.get_client(client_id)
        assert client.status == ClientStatus.OFFLINE

        api.reconnect(client_id)
        assert client.status == ClientStatus.ACTIVE

    def test_platform_status(self):
        api = GOOSAPI()
        status = api.platform_status()
        assert status["platform"] == "Guardian One Operating System"
        assert status["version"] == "1.0"
        assert status["total_clients"] == 0


# ---------------------------------------------------------------------------
# Sentinel tests
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# GOOS Database tests
# ---------------------------------------------------------------------------

class TestGOOSDatabase:
    def test_save_and_load_client(self, tmp_path):
        from guardian_one.goos.database import GOOSDatabase
        db = GOOSDatabase(db_path=tmp_path / "test.db")
        client = GOOSClient(
            client_id="db-test-1",
            email="db@test.com",
            display_name="DB Test",
            tier=ClientTier.PREMIUM,
            status=ClientStatus.ACTIVE,
            agents_enabled=["guardian", "cfo"],
        )
        db.save_client(client)
        loaded = db.load_client("db-test-1")
        assert loaded is not None
        assert loaded.email == "db@test.com"
        assert loaded.tier == ClientTier.PREMIUM
        assert "cfo" in loaded.agents_enabled
        db.close()

    def test_load_by_email(self, tmp_path):
        from guardian_one.goos.database import GOOSDatabase
        db = GOOSDatabase(db_path=tmp_path / "test.db")
        client = GOOSClient(
            client_id="email-test",
            email="find@me.com",
            display_name="Find Me",
        )
        db.save_client(client)
        loaded = db.load_client_by_email("find@me.com")
        assert loaded is not None
        assert loaded.client_id == "email-test"
        db.close()

    def test_save_with_varys_node(self, tmp_path):
        from guardian_one.goos.database import GOOSDatabase
        db = GOOSDatabase(db_path=tmp_path / "test.db")
        client = GOOSClient(
            client_id="node-test",
            email="node@test.com",
            display_name="Node Test",
        )
        client.varys_nodes.append(VarysNode(
            node_id="n1", hostname="laptop", os_type="linux",
            installed_at="2026-01-01", last_seen="2026-01-01",
        ))
        db.save_client(client)
        loaded = db.load_client("node-test")
        assert len(loaded.varys_nodes) == 1
        assert loaded.varys_nodes[0].hostname == "laptop"
        db.close()

    def test_client_count(self, tmp_path):
        from guardian_one.goos.database import GOOSDatabase
        db = GOOSDatabase(db_path=tmp_path / "test.db")
        assert db.client_count() == 0
        db.save_client(GOOSClient(
            client_id="c1", email="a@b.com", display_name="A",
        ))
        db.save_client(GOOSClient(
            client_id="c2", email="c@d.com", display_name="C",
        ))
        assert db.client_count() == 2
        db.close()

    def test_delete_client(self, tmp_path):
        from guardian_one.goos.database import GOOSDatabase
        db = GOOSDatabase(db_path=tmp_path / "test.db")
        db.save_client(GOOSClient(
            client_id="del-me", email="del@me.com", display_name="Del",
        ))
        assert db.delete_client("del-me")
        assert db.load_client("del-me") is None
        db.close()

    def test_registry_bridge(self, tmp_path):
        from guardian_one.goos.database import GOOSDatabase
        db = GOOSDatabase(db_path=tmp_path / "test.db")

        # Save via registry
        reg = ClientRegistry()
        c = reg.create_client("bridge@test.com", "Bridge")
        db.save_from_registry(reg)

        # Load into new registry
        reg2 = ClientRegistry()
        loaded = db.load_into_registry(reg2)
        assert loaded == 1
        assert reg2.get_by_email("bridge@test.com") is not None
        db.close()

    def test_session_management(self, tmp_path):
        from guardian_one.goos.database import GOOSDatabase
        db = GOOSDatabase(db_path=tmp_path / "test.db")
        db.save_client(GOOSClient(
            client_id="sess-test", email="s@t.com", display_name="S",
        ))
        db.create_session("sess-test", "tok-123", "127.0.0.1")
        assert db.validate_session("tok-123") == "sess-test"
        assert db.validate_session("bad-token") is None
        db.invalidate_session("tok-123")
        assert db.validate_session("tok-123") is None
        db.close()


# ---------------------------------------------------------------------------
# Sentinel tests
# ---------------------------------------------------------------------------

class TestVarysSentinel:
    def test_install_generates_service(self, tmp_path):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(
            client_id="test-client",
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "log"),
        )
        result = sentinel.install()
        assert result["client_id"] == "test-client"
        assert "GOOS Varys Sentinel" in result["service_content"]
        assert "goos-varys.service" in result["service_unit"]

    def test_status_before_start(self, tmp_path):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(
            client_id="test",
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "log"),
        )
        status = sentinel.status()
        assert not status.running
        assert status.client_id == "test"

    def test_start_stop(self, tmp_path):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(
            client_id="test",
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "log"),
        )
        sentinel.start()
        assert sentinel.status().running
        sentinel.stop()
        assert not sentinel.status().running

    def test_go_offline(self, tmp_path):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(
            client_id="test",
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "log"),
        )
        sentinel.start()
        sentinel.go_offline()
        assert sentinel.status().tunnel_status == "offline_mode"

    def test_queue_for_sync(self, tmp_path):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(
            client_id="test",
            data_dir=str(tmp_path / "data"),
            log_dir=str(tmp_path / "log"),
        )
        sentinel.queue_for_sync({"type": "alert", "data": "test"})
        assert len(sentinel._queued_sync) == 1

    def test_defaults_fall_back_to_user_writable(self, monkeypatch, tmp_path):
        """When privileged paths aren't writable, resolver uses XDG fallbacks."""
        from guardian_one.goos import sentinel as sentinel_mod
        # Force the privileged paths to point somewhere unwritable so the
        # fallback branch is exercised even when the test runs as root.
        unwritable = str(tmp_path / "nonexistent" / "parent" / "privileged")
        monkeypatch.setattr(sentinel_mod, "_PRIVILEGED_DATA_DIR", unwritable)
        monkeypatch.setattr(sentinel_mod, "_PRIVILEGED_LOG_DIR", unwritable)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg_data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg_state"))
        monkeypatch.delenv("GOOS_DATA_DIR", raising=False)
        monkeypatch.delenv("GOOS_LOG_DIR", raising=False)

        sentinel = sentinel_mod.VarysSentinel(client_id="fallback-test")
        # With privileged paths unwritable, resolver falls back to XDG dirs
        assert str(sentinel.data_dir) == str(tmp_path / "xdg_data" / "goos")
        assert str(sentinel.log_dir) == str(tmp_path / "xdg_state" / "goos" / "log")

    def test_env_var_overrides_default(self, monkeypatch, tmp_path):
        """GOOS_DATA_DIR / GOOS_LOG_DIR env vars override defaults."""
        from guardian_one.goos.sentinel import VarysSentinel
        monkeypatch.setenv("GOOS_DATA_DIR", str(tmp_path / "env_data"))
        monkeypatch.setenv("GOOS_LOG_DIR", str(tmp_path / "env_log"))

        sentinel = VarysSentinel(client_id="env-test")
        assert str(sentinel.data_dir) == str(tmp_path / "env_data")
        assert str(sentinel.log_dir) == str(tmp_path / "env_log")
