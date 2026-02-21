"""Tests for encryption utilities."""

import tempfile
from pathlib import Path

from guardian_one.utils.encryption import (
    decrypt_bytes,
    decrypt_file,
    derive_key_from_passphrase,
    encrypt_bytes,
    encrypt_file,
    generate_key,
)


# ------------------------------------------------------------------
# Key generation
# ------------------------------------------------------------------


def test_generate_key_returns_bytes():
    key = generate_key()
    assert isinstance(key, bytes)
    assert len(key) > 0


def test_generate_key_unique():
    k1 = generate_key()
    k2 = generate_key()
    assert k1 != k2


# ------------------------------------------------------------------
# Key derivation
# ------------------------------------------------------------------


def test_derive_key_from_passphrase():
    key = derive_key_from_passphrase("my-secret-passphrase")
    assert isinstance(key, bytes)
    assert len(key) > 0


def test_derive_key_deterministic():
    k1 = derive_key_from_passphrase("same-pass", salt=b"same-salt")
    k2 = derive_key_from_passphrase("same-pass", salt=b"same-salt")
    assert k1 == k2


def test_derive_key_different_passphrases():
    k1 = derive_key_from_passphrase("pass1")
    k2 = derive_key_from_passphrase("pass2")
    assert k1 != k2


def test_derive_key_different_salts():
    k1 = derive_key_from_passphrase("same", salt=b"salt-a")
    k2 = derive_key_from_passphrase("same", salt=b"salt-b")
    assert k1 != k2


def test_derive_key_default_salt():
    key = derive_key_from_passphrase("test")
    assert key is not None


# ------------------------------------------------------------------
# Bytes encryption/decryption
# ------------------------------------------------------------------


def test_encrypt_decrypt_bytes_roundtrip():
    key = generate_key()
    plaintext = b"Hello, Guardian One!"
    encrypted = encrypt_bytes(plaintext, key)
    decrypted = decrypt_bytes(encrypted, key)
    assert decrypted == plaintext


def test_encrypt_bytes_produces_different_output():
    key = generate_key()
    data = b"same data"
    e1 = encrypt_bytes(data, key)
    e2 = encrypt_bytes(data, key)
    # Fernet uses random IV, so ciphertexts should differ
    assert e1 != e2


def test_encrypt_empty_bytes():
    key = generate_key()
    encrypted = encrypt_bytes(b"", key)
    decrypted = decrypt_bytes(encrypted, key)
    assert decrypted == b""


def test_encrypt_large_bytes():
    key = generate_key()
    data = b"X" * 100_000
    encrypted = encrypt_bytes(data, key)
    decrypted = decrypt_bytes(encrypted, key)
    assert decrypted == data


def test_decrypt_wrong_key_raises():
    k1 = generate_key()
    k2 = generate_key()
    encrypted = encrypt_bytes(b"secret", k1)
    try:
        decrypt_bytes(encrypted, k2)
        assert False, "Should have raised an exception"
    except Exception:
        pass  # Expected: InvalidToken


# ------------------------------------------------------------------
# File encryption/decryption
# ------------------------------------------------------------------


def test_encrypt_decrypt_file_roundtrip():
    key = generate_key()
    tmpdir = Path(tempfile.mkdtemp())
    source = tmpdir / "original.txt"
    encrypted = tmpdir / "encrypted.bin"
    decrypted = tmpdir / "decrypted.txt"

    source.write_text("Guardian One confidential data")
    encrypt_file(source, encrypted, key)

    assert encrypted.exists()
    assert encrypted.read_bytes() != source.read_bytes()

    decrypt_file(encrypted, decrypted, key)
    assert decrypted.read_text() == "Guardian One confidential data"


def test_encrypt_file_empty():
    key = generate_key()
    tmpdir = Path(tempfile.mkdtemp())
    source = tmpdir / "empty.txt"
    encrypted = tmpdir / "empty.enc"
    decrypted = tmpdir / "empty.dec"

    source.write_bytes(b"")
    encrypt_file(source, encrypted, key)
    decrypt_file(encrypted, decrypted, key)
    assert decrypted.read_bytes() == b""


def test_encrypt_file_binary():
    key = generate_key()
    tmpdir = Path(tempfile.mkdtemp())
    source = tmpdir / "binary.dat"
    encrypted = tmpdir / "binary.enc"
    decrypted = tmpdir / "binary.dec"

    source.write_bytes(bytes(range(256)))
    encrypt_file(source, encrypted, key)
    decrypt_file(encrypted, decrypted, key)
    assert decrypted.read_bytes() == bytes(range(256))


# ------------------------------------------------------------------
# Derived key with file encryption
# ------------------------------------------------------------------


def test_derived_key_file_roundtrip():
    key = derive_key_from_passphrase("file-encryption-test", salt=b"test-salt")
    tmpdir = Path(tempfile.mkdtemp())
    source = tmpdir / "data.txt"
    encrypted = tmpdir / "data.enc"
    decrypted = tmpdir / "data.dec"

    source.write_text("encrypted with derived key")
    encrypt_file(source, encrypted, key)
    decrypt_file(encrypted, decrypted, key)
    assert decrypted.read_text() == "encrypted with derived key"
