"""Credential CRUD and validation with policy checks."""

from __future__ import annotations

from typing import Any, Callable, Awaitable
import structlog

from jobos.vault.encryption import encrypt_credential, decrypt_credential

logger = structlog.get_logger(__name__)

async def _dummy_validator(plaintext: str) -> bool:
    """Placeholder validator — real validators will call the provider's API."""
    return bool(plaintext and len(plaintext) > 5)

# Provider names to validation callables.
# Real validators call the provider API to test the key (v3.1 §3.1).
VALIDATORS: dict[str, Callable[[str], Awaitable[bool]]] = {
    "groq": _dummy_validator,
    "openrouter": _dummy_validator,
    "nim": _dummy_validator,
    "cloudflare": _dummy_validator,
    "apollo": _dummy_validator,
    "icypeas": _dummy_validator,
    "google": _dummy_validator,
    "linkedin": _dummy_validator,
}

# What each key unlocks — shown to the user at credential entry.
UNLOCKS: dict[str, str] = {
    "groq": "Job matching and JD parsing",
    "openrouter": "Resume tailoring and outreach drafting",
    "nim": "Fabrication checks — REQUIRED, must differ from your tailoring provider",
    "cloudflare": "Embedding generation for vector search",
    "apollo": "Finding people at your target companies",
    "icypeas": "Warm paths — shared school, past employer",
    "google": "Interview detection and calendar",
    "linkedin": "Publishing posts and comments",
}

# Map providers to model families for the cross-family entailment check.
# If tailor and verifier resolve to the same family, autonomous tailoring is REFUSED.
MODEL_FAMILIES: dict[str, str] = {
    "groq": "llama",
    "openrouter": "mixed",  # depends on which model they select
    "nim": "llama",
    "cloudflare": "bge",    # embeddings only, not used for tailoring
}

async def store_credential(
    conn: Any, tenant_id: str, provider: str, kind: str, plaintext: str, dek: bytes
) -> None:
    """Encrypts and stores a credential in the database."""
    ciphertext, nonce = encrypt_credential(plaintext, dek)
    # Placeholder for actual DB insertion logic
    logger.info("Credential stored", tenant_id=tenant_id, provider=provider, kind=kind)

async def retrieve_credential(
    conn: Any, tenant_id: str, provider: str, dek: bytes
) -> str:
    """Retrieves and decrypts a credential from the database."""
    # Placeholder for actual DB retrieval logic
    ciphertext = b""
    nonce = b""
    return decrypt_credential(ciphertext, nonce, dek)

async def validate_credential(provider: str, plaintext: str) -> bool:
    """Tests if a given credential plaintext is valid for the provider."""
    validator = VALIDATORS.get(provider)
    if not validator:
        raise ValueError(f"No validator for provider: {provider}")
    return await validator(plaintext)

async def check_cross_family(conn: Any, tenant_id: str) -> bool:
    """
    Checks if the tailoring model and verification model resolve to the same model family.
    Returns True if they are the same family, meaning autonomous tailoring must be refused.
    """
    # Placeholder for retrieving tenant's specific models
    tailor_model = "groq"
    verifier_model = "nvidia_nim"
    
    tailor_family = MODEL_FAMILIES.get(tailor_model)
    verifier_family = MODEL_FAMILIES.get(verifier_model)
    
    return bool(tailor_family and verifier_family and tailor_family == verifier_family)
