"""Unit tests for AES-256-GCM envelope encryption."""

import pytest
from cryptography.exceptions import InvalidTag

from jobos.vault.encryption import generate_dek, encrypt_credential, decrypt_credential


def test_generate_dek_is_32_bytes() -> None:
    """DEK must be exactly 32 bytes (256 bits) for AES-256."""
    dek = generate_dek()
    assert len(dek) == 32


def test_generate_dek_is_random() -> None:
    """Two consecutive DEK generations must produce different keys."""
    dek1 = generate_dek()
    dek2 = generate_dek()
    assert dek1 != dek2


def test_encrypt_decrypt_roundtrip() -> None:
    """Encrypting then decrypting must return the original plaintext."""
    dek = generate_dek()
    plaintext = "sk-or-v1-test-key-abcdef1234567890"
    ciphertext, nonce = encrypt_credential(plaintext, dek)
    decrypted = decrypt_credential(ciphertext, nonce, dek)
    assert decrypted == plaintext


def test_wrong_dek_fails_decrypt() -> None:
    """Decrypting with the wrong DEK must raise an error."""
    dek1 = generate_dek()
    dek2 = generate_dek()
    plaintext = "sk-or-v1-test-key-abcdef1234567890"
    ciphertext, nonce = encrypt_credential(plaintext, dek1)
    with pytest.raises(InvalidTag):
        decrypt_credential(ciphertext, nonce, dek2)


def test_different_nonce_per_encryption() -> None:
    """Same plaintext + same DEK must produce different ciphertexts (unique nonce)."""
    dek = generate_dek()
    plaintext = "sk-or-v1-test-key-abcdef1234567890"
    ciphertext1, nonce1 = encrypt_credential(plaintext, dek)
    ciphertext2, nonce2 = encrypt_credential(plaintext, dek)
    assert nonce1 != nonce2
    assert ciphertext1 != ciphertext2


def test_dek_deletion_makes_data_unrecoverable() -> None:
    """Once the DEK is lost, the ciphertext is permanently unrecoverable."""
    dek = generate_dek()
    plaintext = "sk-or-v1-test-key-abcdef1234567890"
    ciphertext, nonce = encrypt_credential(plaintext, dek)
    # Simulate DEK deletion by using a random different key
    lost_dek = generate_dek()
    with pytest.raises(InvalidTag):
        decrypt_credential(ciphertext, nonce, lost_dek)


def test_encrypt_unicode_content() -> None:
    """Must correctly handle Unicode characters (Hinglish/Telugu content)."""
    dek = generate_dek()
    plaintext = "తెలుగు test key — हिंदी 🔑"
    ciphertext, nonce = encrypt_credential(plaintext, dek)
    decrypted = decrypt_credential(ciphertext, nonce, dek)
    assert decrypted == plaintext


def test_nonce_is_12_bytes() -> None:
    """AES-GCM nonce must be exactly 12 bytes per NIST recommendation."""
    dek = generate_dek()
    _, nonce = encrypt_credential("test", dek)
    assert len(nonce) == 12
