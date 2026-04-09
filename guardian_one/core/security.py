"""Security module: encryption, access control, authentication."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64


class AccessLevel(Enum):
    """Role-based access levels for agents and users."""
    OWNER = "owner"          # Jeremy — full access
    GUARDIAN = "guardian"     # Guardian One — system-wide coordination
    AGENT = "agent"          # Subordinate agents — scoped access
    READONLY = "readonly"    # Auditors / read-only views
    MENTOR = "mentor"        # Mentor ("Just") — review access


@dataclass
class AccessPolicy:
    """Defines what an identity is allowed to do."""
    identity: str
    level: AccessLevel
    allowed_resources: list[str] = field(default_factory=list)
    denied_resources: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SecretStore:
    """Encrypted key-value store for sensitive data.

    Uses Fernet symmetric encryption derived from a master passphrase.
    The encryption key never touches disk in plaintext.

    On first creation a random 16-byte salt is generated and stored as a
    prefix on the encrypted file.  Existing files that used the legacy
    static salt are detected and loaded transparently.

    File format (v2):
        GUARDIAN_SALT_V2 (16 bytes marker) || salt (16 bytes) || ciphertext
    Legacy format:
        raw Fernet ciphertext (no marker)
    """

    _SALT_MARKER = b"GUARDIAN_SALT_V2"  # exactly 16 bytes
    _SALT_LENGTH = 16
    _LEGACY_SALT = b"guardian-one-static-salt-v1"

    def __init__(self, store_path: Path, passphrase: str) -> None:
        self._store_path = store_path
        self._data: dict[str, str] = {}

        if self._store_path.exists():
            raw = self._store_path.read_bytes()
            if raw[:len(self._SALT_MARKER)] == self._SALT_MARKER:
                offset = len(self._SALT_MARKER)
                self._salt = raw[offset:offset + self._SALT_LENGTH]
            else:
                self._salt = self._LEGACY_SALT
            self._fernet = self._derive_key(passphrase, self._salt)
            self._load()
        else:
            self._salt = os.urandom(self._SALT_LENGTH)
            self._fernet = self._derive_key(passphrase, self._salt)

    @staticmethod
    def _derive_key(passphrase: str, salt: bytes) -> Fernet:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        return Fernet(key)

    def _load(self) -> None:
        try:
            raw = self._store_path.read_bytes()
            if raw[:len(self._SALT_MARKER)] == self._SALT_MARKER:
                ciphertext = raw[len(self._SALT_MARKER) + self._SALT_LENGTH:]
            else:
                ciphertext = raw
            plaintext = self._fernet.decrypt(ciphertext)
            self._data = json.loads(plaintext)
        except Exception as exc:
            raise ValueError("Failed to unlock secret store") from exc

    def _save(self) -> None:
        plaintext = json.dumps(self._data).encode()
        encrypted = self._fernet.encrypt(plaintext)
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to temp file, then rename to prevent corruption
        tmp_path = self._store_path.with_suffix(".tmp")
        tmp_path.write_bytes(self._SALT_MARKER + self._salt + encrypted)
        tmp_path.replace(self._store_path)

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def keys(self) -> list[str]:
        return list(self._data.keys())


class AccessController:
    """Enforces role-based access control across the agent system."""

    def __init__(self) -> None:
        self._policies: dict[str, AccessPolicy] = {}

    def register(self, policy: AccessPolicy) -> None:
        self._policies[policy.identity] = policy

    def check(self, identity: str, resource: str) -> bool:
        policy = self._policies.get(identity)
        if policy is None:
            return False
        if policy.level == AccessLevel.OWNER:
            return True
        if resource in policy.denied_resources:
            return False
        if policy.allowed_resources and resource not in policy.allowed_resources:
            return False
        return True

    def get_policy(self, identity: str) -> AccessPolicy | None:
        return self._policies.get(identity)

    def list_identities(self) -> list[str]:
        return list(self._policies.keys())


def generate_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def hash_data(data: str) -> str:
    """SHA-256 hash for integrity checks."""
    return hashlib.sha256(data.encode()).hexdigest()


def verify_integrity(data: str, expected_hash: str) -> bool:
    """Constant-time comparison of data hash against expected hash."""
    return hmac.compare_digest(hash_data(data), expected_hash)
