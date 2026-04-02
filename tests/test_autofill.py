"""Tests for the Autofill Bridge — profiles, tokens, server, and fill maps."""

import json
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from guardian_one.core.audit import AuditLog
from guardian_one.core.config import AgentConfig
from guardian_one.homelink.vault import Vault
from guardian_one.agents.autofill import (
    AutofillAgent,
    _build_fill_map,
    _generate_token,
    _consume_token,
    _cleanup_expired_tokens,
    _pending_tokens,
    TOKEN_TTL_SECONDS,
)
from guardian_one.autofill.profiles import (
    CardProfile,
    AddressProfile,
    IdentityProfile,
    CARD_PREFIX,
    ADDRESS_PREFIX,
    IDENTITY_PREFIX,
)
from guardian_one.autofill.bridge import get_bookmarklet_js


def _make_audit() -> AuditLog:
    return AuditLog(log_dir=Path(tempfile.mkdtemp()))


def _make_vault(tmpdir: str) -> Vault:
    return Vault(Path(tmpdir) / "vault.enc", passphrase="test-pass")


def _make_agent(vault: Vault, port: int = 0) -> AutofillAgent:
    cfg = AgentConfig(name="autofill", custom={"autofill_port": port})
    agent = AutofillAgent(config=cfg, audit=_make_audit(), vault=vault)
    agent.initialize()
    return agent


# ========================================================================
# Profile model tests
# ========================================================================

class TestCardProfile:
    def test_roundtrip_json(self):
        card = CardProfile(
            label="Test Card",
            cardholder_name="John Doe",
            card_number="4111111111111111",
            exp_month="12",
            exp_year="2027",
            cvv="123",
        )
        restored = CardProfile.from_json(card.to_json())
        assert restored.label == "Test Card"
        assert restored.card_number == "4111111111111111"
        assert restored.cvv == "123"

    def test_masked_number(self):
        card = CardProfile(
            label="x", cardholder_name="x",
            card_number="4111111111111111",
            exp_month="01", exp_year="2028", cvv="999",
        )
        assert card.masked_number == "****1111"

    def test_masked_number_short(self):
        card = CardProfile(
            label="x", cardholder_name="x",
            card_number="12",
            exp_month="01", exp_year="2028", cvv="0",
        )
        assert card.masked_number == "****"

    def test_exp_combined(self):
        card = CardProfile(
            label="x", cardholder_name="x",
            card_number="x", exp_month="03", exp_year="2026", cvv="0",
        )
        assert card.exp_combined == "03/2026"


class TestAddressProfile:
    def test_roundtrip_json(self):
        addr = AddressProfile(
            label="Home", full_name="J Doe",
            street="123 Main St", city="Dallas",
            state="TX", zip_code="75001",
        )
        restored = AddressProfile.from_json(addr.to_json())
        assert restored.city == "Dallas"
        assert restored.country == "US"


class TestIdentityProfile:
    def test_roundtrip_json(self):
        ident = IdentityProfile(
            label="Personal", first_name="Jeremy",
            last_name="Tabernero", email="j@example.com",
        )
        restored = IdentityProfile.from_json(ident.to_json())
        assert restored.first_name == "Jeremy"
        assert restored.email == "j@example.com"


# ========================================================================
# Token tests
# ========================================================================

class TestTokens:
    def setup_method(self):
        _pending_tokens.clear()

    def test_generate_and_consume(self):
        token = _generate_token("card", "abc123")
        assert len(token) > 20
        result = _consume_token(token)
        assert result == ("card", "abc123")

    def test_consume_only_once(self):
        token = _generate_token("card", "abc123")
        assert _consume_token(token) is not None
        assert _consume_token(token) is None  # Second use fails

    def test_invalid_token(self):
        assert _consume_token("bogus-token-12345") is None

    def test_expired_token(self):
        token = _generate_token("card", "abc123")
        # Manually expire it
        ptype, pid, _ = _pending_tokens[token]
        _pending_tokens[token] = (ptype, pid, time.time() - TOKEN_TTL_SECONDS - 1)
        assert _consume_token(token) is None

    def test_cleanup_expired(self):
        _generate_token("card", "a")
        _generate_token("card", "b")
        # Expire both
        for t in list(_pending_tokens.keys()):
            ptype, pid, _ = _pending_tokens[t]
            _pending_tokens[t] = (ptype, pid, time.time() - TOKEN_TTL_SECONDS - 1)
        removed = _cleanup_expired_tokens()
        assert removed == 2
        assert len(_pending_tokens) == 0


# ========================================================================
# AutofillAgent CRUD tests
# ========================================================================

class TestAutofillAgent:
    def test_add_and_list_card(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            card = agent.add_card(
                label="Chase Sapphire",
                cardholder_name="Jeremy Tabernero",
                card_number="4111111111111111",
                exp_month="12", exp_year="2027", cvv="321",
                billing_address="123 Main St", billing_zip="75001",
            )
            profiles = agent.list_profiles()
            assert len(profiles) == 1
            assert profiles[0]["label"] == "Chase Sapphire"
            assert profiles[0]["masked_number"] == "****1111"
            assert profiles[0]["type"] == "card"

    def test_add_and_list_address(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            agent.add_address(
                label="Home", full_name="Jeremy",
                street="456 Oak", city="Dallas", state="TX", zip_code="75001",
            )
            profiles = agent.list_profiles("address")
            assert len(profiles) == 1
            assert profiles[0]["label"] == "Home"

    def test_add_and_list_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            agent.add_identity(
                label="Personal", first_name="Jeremy",
                last_name="Tabernero", email="j@test.com",
            )
            profiles = agent.list_profiles("identity")
            assert len(profiles) == 1

    def test_get_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            card = agent.add_card(
                label="Amex", cardholder_name="Jeremy",
                card_number="378282246310005",
                exp_month="06", exp_year="2028", cvv="1234",
            )
            data = agent.get_profile("card", card.profile_id)
            assert data is not None
            assert data["card_number"] == "378282246310005"
            assert data["cvv"] == "1234"

    def test_get_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            assert agent.get_profile("card", "nope") is None
            assert agent.get_profile("bogus", "nope") is None

    def test_remove_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            card = agent.add_card(
                label="Temp", cardholder_name="X",
                card_number="4111111111111111",
                exp_month="01", exp_year="2025", cvv="000",
            )
            assert agent.remove_profile("card", card.profile_id) is True
            assert agent.list_profiles() == []
            assert agent.remove_profile("card", card.profile_id) is False

    def test_list_filters_by_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            agent.add_card(
                label="C1", cardholder_name="X",
                card_number="4111111111111111",
                exp_month="01", exp_year="2025", cvv="0",
            )
            agent.add_address(
                label="A1", full_name="X",
                street="1", city="X", state="X", zip_code="0",
            )
            assert len(agent.list_profiles("card")) == 1
            assert len(agent.list_profiles("address")) == 1
            assert len(agent.list_profiles()) == 2

    def test_fill_token(self):
        _pending_tokens.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            card = agent.add_card(
                label="Test", cardholder_name="X",
                card_number="4111111111111111",
                exp_month="01", exp_year="2025", cvv="0",
            )
            token = agent.request_fill_token("card", card.profile_id)
            assert token is not None
            # Token should be consumable
            result = _consume_token(token)
            assert result == ("card", card.profile_id)

    def test_fill_token_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            assert agent.request_fill_token("card", "nope") is None

    def test_run_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault)
            agent.add_card(
                label="X", cardholder_name="X",
                card_number="4111111111111111",
                exp_month="01", exp_year="2025", cvv="0",
            )
            report = agent.run()
            assert report.agent_name == "autofill"
            assert report.status == "ok"
            assert report.data["cards"] == 1
            assert report.data["server_running"] is False


# ========================================================================
# Fill map tests
# ========================================================================

class TestFillMap:
    def test_card_fill_map(self):
        data = {
            "cardholder_name": "Jeremy",
            "card_number": "4111111111111111",
            "exp_month": "12",
            "exp_year": "2027",
            "cvv": "321",
            "billing_address": "123 Main",
            "billing_zip": "75001",
        }
        fill = _build_fill_map("card", data)
        values = [f["value"] for f in fill["fields"]]
        assert "Jeremy" in values
        assert "4111111111111111" in values
        assert "321" in values
        assert "12/2027" in values  # Combined expiry

    def test_address_fill_map(self):
        data = {
            "full_name": "Jeremy",
            "street": "123 Main",
            "city": "Dallas",
            "state": "TX",
            "zip_code": "75001",
            "country": "US",
            "phone": "555-1234",
        }
        fill = _build_fill_map("address", data)
        values = [f["value"] for f in fill["fields"]]
        assert "Dallas" in values
        assert "TX" in values

    def test_identity_fill_map(self):
        data = {
            "first_name": "Jeremy",
            "last_name": "Tabernero",
            "email": "j@test.com",
            "phone": "555",
            "date_of_birth": "1990-01-01",
        }
        fill = _build_fill_map("identity", data)
        values = [f["value"] for f in fill["fields"]]
        assert "Jeremy" in values
        assert "j@test.com" in values

    def test_unknown_type_empty(self):
        fill = _build_fill_map("unknown", {})
        assert fill["fields"] == []


# ========================================================================
# Bookmarklet generation tests
# ========================================================================

class TestBookmarklet:
    def test_bookmarklet_contains_port(self):
        js = get_bookmarklet_js(17380)
        assert "127.0.0.1:17380" in js
        assert "Guardian Autofill" in js

    def test_bookmarklet_custom_port(self):
        js = get_bookmarklet_js(9999)
        assert "127.0.0.1:9999" in js


# ========================================================================
# Local server integration tests
# ========================================================================

class TestAutofillServer:
    def test_server_start_stop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            # Use port 0 to let OS pick a free port — but our server
            # needs a known port, so pick a high ephemeral one
            agent = _make_agent(vault, port=17399)
            url = agent.start_server()
            assert "127.0.0.1" in url
            try:
                # Health check
                req = urllib.request.Request(f"{url}/api/autofill/health")
                resp = urllib.request.urlopen(req, timeout=2)
                data = json.loads(resp.read())
                assert data["status"] == "ok"
            finally:
                agent.stop_server()

    def test_server_profiles_endpoint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault, port=17398)
            agent.add_card(
                label="Test", cardholder_name="X",
                card_number="4111111111111111",
                exp_month="01", exp_year="2025", cvv="0",
            )
            url = agent.start_server()
            try:
                req = urllib.request.Request(f"{url}/api/autofill/profiles")
                resp = urllib.request.urlopen(req, timeout=2)
                data = json.loads(resp.read())
                assert len(data["profiles"]) == 1
                assert data["profiles"][0]["label"] == "Test"
            finally:
                agent.stop_server()

    def test_server_token_and_fill_flow(self):
        _pending_tokens.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault, port=17397)
            card = agent.add_card(
                label="Flow", cardholder_name="Jeremy",
                card_number="4111111111111111",
                exp_month="06", exp_year="2028", cvv="555",
            )
            url = agent.start_server()
            try:
                # Request token
                token_body = json.dumps({
                    "type": "card",
                    "profile_id": card.profile_id,
                }).encode()
                req = urllib.request.Request(
                    f"{url}/api/autofill/token",
                    data=token_body,
                    headers={"Content-Type": "application/json"},
                )
                resp = urllib.request.urlopen(req, timeout=2)
                token_data = json.loads(resp.read())
                assert "token" in token_data

                # Use token to fill
                fill_body = json.dumps({
                    "token": token_data["token"],
                }).encode()
                req = urllib.request.Request(
                    f"{url}/api/autofill/fill",
                    data=fill_body,
                    headers={"Content-Type": "application/json"},
                )
                resp = urllib.request.urlopen(req, timeout=2)
                fill_data = json.loads(resp.read())
                assert fill_data["type"] == "card"
                values = [f["value"] for f in fill_data["fill"]["fields"]]
                assert "4111111111111111" in values
                assert "555" in values
            finally:
                agent.stop_server()

    def test_server_rejects_reused_token(self):
        _pending_tokens.clear()
        with tempfile.TemporaryDirectory() as tmpdir:
            vault = _make_vault(tmpdir)
            agent = _make_agent(vault, port=17396)
            card = agent.add_card(
                label="X", cardholder_name="X",
                card_number="4111111111111111",
                exp_month="01", exp_year="2025", cvv="0",
            )
            url = agent.start_server()
            try:
                # Get token
                token_body = json.dumps({
                    "type": "card",
                    "profile_id": card.profile_id,
                }).encode()
                req = urllib.request.Request(
                    f"{url}/api/autofill/token",
                    data=token_body,
                    headers={"Content-Type": "application/json"},
                )
                resp = urllib.request.urlopen(req, timeout=2)
                token_data = json.loads(resp.read())

                # Use token once (success)
                fill_body = json.dumps({"token": token_data["token"]}).encode()
                req = urllib.request.Request(
                    f"{url}/api/autofill/fill",
                    data=fill_body,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=2)

                # Use same token again (should fail 403)
                req = urllib.request.Request(
                    f"{url}/api/autofill/fill",
                    data=fill_body,
                    headers={"Content-Type": "application/json"},
                )
                with pytest.raises(urllib.error.HTTPError) as exc:
                    urllib.request.urlopen(req, timeout=2)
                assert exc.value.code == 403
            finally:
                agent.stop_server()
