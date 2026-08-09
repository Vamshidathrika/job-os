"""KMS wrapper for wrapping/unwrapping tenant DEKs."""

from __future__ import annotations

import binascii
import os
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import structlog

from jobos.config import VaultSettings

logger = structlog.get_logger(__name__)


class KMSProvider(Protocol):
    """Abstract interface for Key Management Service providers."""
    
    def wrap_dek(self, plaintext_dek: bytes) -> bytes:
        """Encrypt the DEK using the master key."""
        ...
        
    def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        """Decrypt the DEK using the master key."""
        ...


class LocalKMS(KMSProvider):
    """Dev-only KMS using a static master key."""
    
    def __init__(self, master_key_hex: str) -> None:
        """Initialize LocalKMS with a hex-encoded master key."""
        self.master_key = binascii.unhexlify(master_key_hex)
        if len(self.master_key) != 32:
            raise ValueError("Local master key must be 32 bytes.")

    def wrap_dek(self, plaintext_dek: bytes) -> bytes:
        """Encrypts the DEK using the master key."""
        aesgcm = AESGCM(self.master_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext_dek, None)
        return nonce + ciphertext

    def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        """Decrypts the DEK using the master key."""
        aesgcm = AESGCM(self.master_key)
        nonce = wrapped_dek[:12]
        ciphertext = wrapped_dek[12:]
        return aesgcm.decrypt(nonce, ciphertext, None)


class AWSKMS(KMSProvider):
    """Placeholder for AWS KMS integration."""
    
    def __init__(self, key_id: str, region: str) -> None:
        """Initialize AWSKMS with key details."""
        self.key_id = key_id
        self.region = region

    def wrap_dek(self, plaintext_dek: bytes) -> bytes:
        """Encrypts the DEK using AWS KMS."""
        raise NotImplementedError("AWS KMS wrap_dek not implemented")

    def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        """Decrypts the DEK using AWS KMS."""
        raise NotImplementedError("AWS KMS unwrap_dek not implemented")


def get_kms(settings: VaultSettings) -> KMSProvider:
    """Factory to get the appropriate KMS provider based on settings."""
    if settings.kms_provider == "local":
        return LocalKMS(settings.local_master_key_hex)
    elif settings.kms_provider == "aws":
        return AWSKMS(settings.aws_kms_key_id, settings.aws_region)
    else:
        raise ValueError(f"Unknown KMS provider: {settings.kms_provider}")
