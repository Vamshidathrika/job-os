"""KMS wrapper for wrapping/unwrapping tenant DEKs."""

from __future__ import annotations

import binascii
import os
from typing import Any, Protocol

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
    """AWS KMS-backed envelope encryption.

    A 32-byte DEK is far below the 4KB limit for direct KMS Encrypt, so the
    DEK is wrapped by KMS itself rather than by a locally derived key. The
    returned CiphertextBlob embeds the key id, so Decrypt does not need it.
    """

    def __init__(self, key_id: str, region: str) -> None:
        """Initialize AWSKMS with key details."""
        if not key_id:
            raise ValueError(
                "JOBOS_VAULT_AWS_KMS_KEY_ID must be set when kms_provider='aws'"
            )
        self.key_id = key_id
        self.region = region
        self._client: Any = None

    @property
    def client(self) -> Any:
        """Lazily construct the boto3 KMS client.

        Imported lazily so that local/dev installs — which do not need AWS —
        are not forced to install boto3.
        """
        if self._client is None:
            try:
                import boto3  # type: ignore[import-not-found,import-untyped]
            except ImportError as e:  # pragma: no cover - depends on install extras
                raise RuntimeError(
                    "boto3 is required for kms_provider='aws'. "
                    "Install it with: pip install 'jobos[aws]'"
                ) from e
            self._client = boto3.client("kms", region_name=self.region)
        return self._client

    def wrap_dek(self, plaintext_dek: bytes) -> bytes:
        """Encrypts the DEK using AWS KMS."""
        response = self.client.encrypt(KeyId=self.key_id, Plaintext=plaintext_dek)
        return bytes(response["CiphertextBlob"])

    def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        """Decrypts the DEK using AWS KMS."""
        response = self.client.decrypt(CiphertextBlob=wrapped_dek, KeyId=self.key_id)
        return bytes(response["Plaintext"])


def get_kms(settings: VaultSettings) -> KMSProvider:
    """Factory to get the appropriate KMS provider based on settings."""
    if settings.kms_provider == "local":
        if settings.environment_is_production:
            raise ValueError(
                "kms_provider='local' is dev-only and must not be used in production"
            )
        return LocalKMS(settings.local_master_key_hex)
    elif settings.kms_provider == "aws":
        return AWSKMS(settings.aws_kms_key_id, settings.aws_region)
    elif settings.kms_provider == "gcp":
        # Deliberately unimplemented rather than silently degraded: shipping a
        # stub here would mean tenant DEKs were never actually wrapped.
        raise NotImplementedError(
            "GCP KMS is not implemented. Use kms_provider='aws', or 'local' for dev."
        )
    else:
        raise ValueError(f"Unknown KMS provider: {settings.kms_provider}")
