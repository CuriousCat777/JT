"""Tests for GOOS — Guardian One Operating System platform layer."""

from __future__ import annotations

import pytest

from guardian_one.goos.client import (
    ClientRegistry,
    ClientStatus,
    ClientTier,
    GOOSClient,
    OnboardingStep,
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

class TestVarysSentinel:
    def test_install_generates_service(self):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(client_id="test-client", data_dir="/tmp/goos-test")
        result = sentinel.install()
        assert result["client_id"] == "test-client"
        assert "GOOS Varys Sentinel" in result["service_content"]
        assert "goos-varys.service" in result["service_unit"]

    def test_status_before_start(self):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(client_id="test", data_dir="/tmp/goos-test")
        status = sentinel.status()
        assert not status.running
        assert status.client_id == "test"

    def test_start_stop(self):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(client_id="test", data_dir="/tmp/goos-test")
        sentinel.start()
        assert sentinel.status().running
        sentinel.stop()
        assert not sentinel.status().running

    def test_go_offline(self):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(client_id="test", data_dir="/tmp/goos-test")
        sentinel.start()
        sentinel.go_offline()
        assert sentinel.status().tunnel_status == "offline_mode"

    def test_queue_for_sync(self):
        from guardian_one.goos.sentinel import VarysSentinel
        sentinel = VarysSentinel(client_id="test", data_dir="/tmp/goos-test")
        sentinel.queue_for_sync({"type": "alert", "data": "test"})
        assert len(sentinel._queued_sync) == 1
