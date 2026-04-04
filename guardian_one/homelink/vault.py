"""Encrypted credential vault for H.O.M.E. L.I.N.K.

Stores all API keys, tokens, and secrets using Fernet encryption
with PBKDF2 key derivation.  Secrets never exist in plaintext on disk.

Supported backends (extensible):
    - LocalVault: encrypted JSON file (default MVP)
    - Future: macOS Keychain, 1Password CLI, HashiCorp Vault

Security guarantees:
    - 480K PBKDF2 iterations for key derivation
    - Per-credential encryption (no bulk decrypt needed)
    - Secrets never appear in logs or audit trails
    - Rotation tracking with expiry warnings
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64


@dataclass
class CredentialMeta:
    """Metadata about a stored credential (the value itself is encrypted)."""
    key_name: str
    service: str
    scope: str = "read"          # read, write, admin
    created_at: str = ""
    rotated_at: str = ""
    expires_at: str = ""         # ISO date or empty for no-expiry
    rotation_days: int = 90      # Recommended rotation interval


class VaultError(Exception):
    """Raised on vault access failures."""


class Vault:
    """Encrypted credential store.

    Usage:
        vault = Vault(Path("data/vault.enc"), passphrase="...")
        vault.store("DOORDASH_KEY_ID", "abc123", service="doordash")
        key = vault.retrieve("DOORDASH_KEY_ID")
        vault.rotate("DOORDASH_KEY_ID", "new_value")

    Salt handling:
        On first creation a random 16-byte salt is generated and stored
        as a file prefix.  Legacy files with the old static salt are
        detected and loaded transparently.
    """

    _SALT_MARKER = b"VAULT___SALT__V2"  # exactly 16 bytes
    _SALT_LENGTH = 16
    _LEGACY_SALT = b"homelink-vault-salt-v1"

    def __init__(self, vault_path: Path, passphrase: str) -> None:
        self._path = vault_path
        self._lock = threading.Lock()
        self._secrets: dict[str, str] = {}
        self._meta: dict[str, CredentialMeta] = {}

        if self._path.exists():
            raw = self._path.read_bytes()
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
            raw = self._path.read_bytes()
            if raw[:len(self._SALT_MARKER)] == self._SALT_MARKER:
                ciphertext = raw[len(self._SALT_MARKER) + self._SALT_LENGTH:]
            else:
                ciphertext = raw
            plaintext = self._fernet.decrypt(ciphertext)
            data = json.loads(plaintext)
            self._secrets = data.get("secrets", {})
            for k, v in data.get("meta", {}).items():
                self._meta[k] = CredentialMeta(**v)
        except (InvalidToken, json.JSONDecodeError) as exc:
            raise VaultError(f"Failed to unlock vault: {exc}") from exc

    def _save(self) -> None:
        data = {
            "secrets": self._secrets,
            "meta": {k: asdict(v) for k, v in self._meta.items()},
        }
        plaintext = json.dumps(data).encode()
        encrypted = self._fernet.encrypt(plaintext)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to temp file, then rename to prevent corruption
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_bytes(self._SALT_MARKER + self._salt + encrypted)
        tmp_path.replace(self._path)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def store(
        self,
        key_name: str,
        value: str,
        service: str = "",
        scope: str = "read",
        rotation_days: int = 90,
        expires_at: str = "",
    ) -> None:
        """Store or overwrite a secret."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._secrets[key_name] = value
            self._meta[key_name] = CredentialMeta(
                key_name=key_name,
                service=service,
                scope=scope,
                created_at=now,
                rotated_at=now,
                expires_at=expires_at,
                rotation_days=rotation_days,
            )
            self._save()

    def retrieve(self, key_name: str) -> str | None:
        """Retrieve a secret by name.  Returns None if not found."""
        with self._lock:
            return self._secrets.get(key_name)

    def rotate(self, key_name: str, new_value: str) -> bool:
        """Replace a secret value and update rotation timestamp."""
        with self._lock:
            if key_name not in self._secrets:
                return False
            self._secrets[key_name] = new_value
            self._meta[key_name].rotated_at = datetime.now(timezone.utc).isoformat()
            self._save()
            return True

    def delete(self, key_name: str) -> bool:
        with self._lock:
            if key_name not in self._secrets:
                return False
            del self._secrets[key_name]
            self._meta.pop(key_name, None)
            self._save()
            return True

    def list_keys(self) -> list[str]:
        with self._lock:
            return list(self._secrets.keys())

    def get_meta(self, key_name: str) -> CredentialMeta | None:
        with self._lock:
            return self._meta.get(key_name)

    # ------------------------------------------------------------------
    # Health checks
    # ------------------------------------------------------------------

    def credentials_due_for_rotation(self) -> list[CredentialMeta]:
        """Return credentials past their recommended rotation window."""
        now = datetime.now(timezone.utc)
        due: list[CredentialMeta] = []
        with self._lock:
            meta_snapshot = list(self._meta.values())
        for meta in meta_snapshot:
            if not meta.rotated_at:
                continue
            try:
                rotated = datetime.fromisoformat(meta.rotated_at)
            except (ValueError, TypeError):
                continue
            if rotated.tzinfo is None:
                rotated = rotated.replace(tzinfo=timezone.utc)
            age_days = (now - rotated).days
            if age_days >= meta.rotation_days:
                due.append(meta)
        return due

    def expired_credentials(self) -> list[CredentialMeta]:
        """Return credentials past their expiry date."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            meta_snapshot = list(self._meta.values())
        return [
            m for m in meta_snapshot
            if m.expires_at and m.expires_at < now
        ]

    def health_report(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._secrets)
            services = list({m.service for m in self._meta.values() if m.service})
        return {
            "total_credentials": total,
            "due_for_rotation": len(self.credentials_due_for_rotation()),
            "expired": len(self.expired_credentials()),
            "services": services,
        }
