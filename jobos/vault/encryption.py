"""AES-256-GCM envelope encryption for credentials."""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import structlog

logger = structlog.get_logger(__name__)


def generate_dek() -> bytes:
    """Generate 32 random bytes for Data Encryption Key."""
    return os.urandom(32)


def encrypt_credential(plaintext: str, dek: bytes) -> tuple[bytes, bytes]:
    """Encrypt a plaintext credential using AES-256-GCM."""
    aesgcm = AESGCM(dek)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)
    return ciphertext, nonce


def decrypt_credential(ciphertext: bytes, nonce: bytes, dek: bytes) -> str:
    """Decrypt a ciphertext credential using AES-256-GCM."""
    aesgcm = AESGCM(dek)
    plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext_bytes.decode('utf-8')
