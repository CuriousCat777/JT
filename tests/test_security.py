"""Tests for the security module."""

import tempfile
from pathlib import Path

from guardian_one.core.security import (
    AccessController,
    AccessLevel,
    AccessPolicy,
    SecretStore,
    generate_token,
    hash_data,
    verify_integrity,
)


def test_access_controller_owner_has_full_access():
    ac = AccessController()
    ac.register(AccessPolicy(identity="jeremy", level=AccessLevel.OWNER))
    assert ac.check("jeremy", "anything") is True
    assert ac.check("jeremy", "financial_records") is True


def test_access_controller_agent_scoped():
    ac = AccessController()
    ac.register(AccessPolicy(
        identity="chronos",
        level=AccessLevel.AGENT,
        allowed_resources=["calendar", "sleep_data"],
    ))
    assert ac.check("chronos", "calendar") is True
    assert ac.check("chronos", "financial_records") is False


def test_access_controller_denied_resources():
    ac = AccessController()
    ac.register(AccessPolicy(
        identity="test_agent",
        level=AccessLevel.AGENT,
        allowed_resources=["calendar", "files"],
        denied_resources=["files"],
    ))
    assert ac.check("test_agent", "files") is False
    assert ac.check("test_agent", "calendar") is True


def test_access_controller_unknown_identity():
    ac = AccessController()
    assert ac.check("unknown", "anything") is False


def test_secret_store_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / "secrets.enc"
        store = SecretStore(store_path, passphrase="test-passphrase")
        store.set("api_key", "sk-12345")
        store.set("password", "hunter2")

        assert store.get("api_key") == "sk-12345"
        assert store.get("password") == "hunter2"
        assert store.get("nonexistent") is None

        # Reload from disk
        store2 = SecretStore(store_path, passphrase="test-passphrase")
        assert store2.get("api_key") == "sk-12345"


def test_secret_store_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / "secrets.enc"
        store = SecretStore(store_path, passphrase="test-passphrase")
        store.set("key", "value")
        assert store.delete("key") is True
        assert store.get("key") is None
        assert store.delete("key") is False


def test_generate_token():
    t1 = generate_token()
    t2 = generate_token()
    assert len(t1) > 20
    assert t1 != t2


def test_hash_and_verify():
    data = "sensitive information"
    h = hash_data(data)
    assert verify_integrity(data, h) is True
    assert verify_integrity("wrong data", h) is False
