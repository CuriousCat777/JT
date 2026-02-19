"""Encryption utilities — wrappers around cryptography library.

Provides file-level encryption for sensitive documents and data exports.
"""

from __future__ import annotations

import base64
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def generate_key() -> bytes:
    """Generate a new Fernet key."""
    return Fernet.generate_key()


def derive_key_from_passphrase(passphrase: str, salt: bytes | None = None) -> bytes:
    """Derive a Fernet key from a passphrase using PBKDF2."""
    if salt is None:
        salt = b"guardian-one-default-salt"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def encrypt_file(source: Path, dest: Path, key: bytes) -> None:
    """Encrypt a file and write the ciphertext to dest."""
    fernet = Fernet(key)
    plaintext = source.read_bytes()
    dest.write_bytes(fernet.encrypt(plaintext))


def decrypt_file(source: Path, dest: Path, key: bytes) -> None:
    """Decrypt a file and write the plaintext to dest."""
    fernet = Fernet(key)
    ciphertext = source.read_bytes()
    dest.write_bytes(fernet.decrypt(ciphertext))


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    return Fernet(key).encrypt(data)


def decrypt_bytes(data: bytes, key: bytes) -> bytes:
    return Fernet(key).decrypt(data)
