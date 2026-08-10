"""Credential CRUD and validation with policy checks."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Awaitable

import httpx
import structlog

from jobos.vault.encryption import encrypt_credential, decrypt_credential

logger = structlog.get_logger(__name__)

# How long to wait on a provider's auth-check endpoint before giving up.
VALIDATION_TIMEOUT_SECONDS = 10.0


class CredentialNotFoundError(LookupError):
    """Raised when a tenant has no stored credential for a provider."""


async def _check_endpoint(
    url: str,
    headers: dict[str, str],
    *,
    provider: str,
    params: dict[str, str] | None = None,
) -> bool:
    """Issue a cheap authenticated GET and report whether the key was accepted.

    Any 2xx means the key works. 401/403 means it does not. Anything else
    (network error, 5xx, rate limit) is inconclusive, so we surface it as
    invalid but log loudly — callers must not treat "provider down" as
    "key is good".
    """
    try:
        async with httpx.AsyncClient(timeout=VALIDATION_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers, params=params)
    except httpx.HTTPError as e:
        logger.error("credential_validation_unreachable", provider=provider, error=str(e))
        return False

    if response.is_success:
        return True
    if response.status_code in (401, 403):
        logger.info("credential_validation_rejected", provider=provider, status=response.status_code)
        return False

    logger.error(
        "credential_validation_inconclusive",
        provider=provider,
        status=response.status_code,
    )
    return False


async def _validate_groq(plaintext: str) -> bool:
    """Validate a Groq API key by listing models."""
    return await _check_endpoint(
        "https://api.groq.com/openai/v1/models",
        {"Authorization": f"Bearer {plaintext}"},
        provider="groq",
    )


async def _validate_openrouter(plaintext: str) -> bool:
    """Validate an OpenRouter API key by reading the key's own metadata."""
    return await _check_endpoint(
        "https://openrouter.ai/api/v1/key",
        {"Authorization": f"Bearer {plaintext}"},
        provider="openrouter",
    )


async def _validate_nim(plaintext: str) -> bool:
    """Validate an NVIDIA NIM key by listing models."""
    return await _check_endpoint(
        "https://integrate.api.nvidia.com/v1/models",
        {"Authorization": f"Bearer {plaintext}"},
        provider="nim",
    )


async def _validate_cloudflare(plaintext: str) -> bool:
    """Validate a Cloudflare API token via the token-verify endpoint."""
    return await _check_endpoint(
        "https://api.cloudflare.com/client/v4/user/tokens/verify",
        {"Authorization": f"Bearer {plaintext}"},
        provider="cloudflare",
    )


async def _validate_apollo(plaintext: str) -> bool:
    """Validate an Apollo key against the auth health endpoint."""
    return await _check_endpoint(
        "https://api.apollo.io/v1/auth/health",
        {"Cache-Control": "no-cache", "Content-Type": "application/json"},
        provider="apollo",
        params={"api_key": plaintext},
    )


async def _validate_icypeas(plaintext: str) -> bool:
    """Validate an Icypeas key by reading the account profile."""
    return await _check_endpoint(
        "https://app.icypeas.com/api/me",
        {"Authorization": plaintext},
        provider="icypeas",
    )


async def _validate_google(plaintext: str) -> bool:
    """Validate a Google OAuth access token via the tokeninfo endpoint."""
    return await _check_endpoint(
        "https://www.googleapis.com/oauth2/v3/tokeninfo",
        {},
        provider="google",
        params={"access_token": plaintext},
    )


async def _validate_linkedin(plaintext: str) -> bool:
    """Validate a LinkedIn member token via the userinfo endpoint."""
    return await _check_endpoint(
        "https://api.linkedin.com/v2/userinfo",
        {"Authorization": f"Bearer {plaintext}"},
        provider="linkedin",
    )


# Provider names to validation callables.
# Each hits the provider's cheapest authenticated endpoint (v3.1 §3.1).
VALIDATORS: dict[str, Callable[[str], Awaitable[bool]]] = {
    "groq": _validate_groq,
    "openrouter": _validate_openrouter,
    "nim": _validate_nim,
    "cloudflare": _validate_cloudflare,
    "apollo": _validate_apollo,
    "icypeas": _validate_icypeas,
    "google": _validate_google,
    "linkedin": _validate_linkedin,
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

# Which stored credential drives which stage of the tailoring pipeline.
TAILORING_ROLE_KINDS = {"tailor", "verifier"}


async def store_credential(
    conn: Any, tenant_id: str, provider: str, kind: str, plaintext: str, dek: bytes
) -> None:
    """Encrypts and stores a credential in the database.

    The plaintext is never persisted or logged — only the AES-256-GCM
    ciphertext, its nonce, and the last 4 characters for display.
    """
    ciphertext, nonce = encrypt_credential(plaintext, dek)
    await conn.execute(
        """
        INSERT INTO credentials (id, tenant_id, provider, kind, ciphertext, nonce, last4, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, 'unvalidated')
        ON CONFLICT (tenant_id, provider) DO UPDATE SET
            kind = EXCLUDED.kind,
            ciphertext = EXCLUDED.ciphertext,
            nonce = EXCLUDED.nonce,
            last4 = EXCLUDED.last4,
            status = 'unvalidated',
            validated_at = NULL,
            last_error = NULL
        """,
        uuid.uuid4(),
        uuid.UUID(str(tenant_id)),
        provider,
        kind,
        ciphertext,
        nonce,
        plaintext[-4:],
    )
    logger.info("credential_stored", tenant_id=tenant_id, provider=provider, kind=kind)


async def retrieve_credential(
    conn: Any, tenant_id: str, provider: str, dek: bytes
) -> str:
    """Retrieves and decrypts a credential from the database.

    Raises:
        CredentialNotFoundError: if the tenant has no credential for provider.
    """
    row = await conn.fetchrow(
        "SELECT ciphertext, nonce FROM credentials WHERE tenant_id = $1 AND provider = $2",
        uuid.UUID(str(tenant_id)),
        provider,
    )
    if row is None or row["ciphertext"] is None or row["nonce"] is None:
        raise CredentialNotFoundError(
            f"No stored credential for provider '{provider}'"
        )
    return decrypt_credential(bytes(row["ciphertext"]), bytes(row["nonce"]), dek)


async def mark_validation_result(
    conn: Any, tenant_id: str, provider: str, is_valid: bool, error: str | None = None
) -> None:
    """Persist the outcome of a validation attempt for a stored credential."""
    await conn.execute(
        """
        UPDATE credentials
        SET status = $3,
            validated_at = CASE WHEN $3 = 'valid' THEN now() ELSE validated_at END,
            last_error = $4
        WHERE tenant_id = $1 AND provider = $2
        """,
        uuid.UUID(str(tenant_id)),
        provider,
        "valid" if is_valid else "invalid",
        error,
    )


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

    Fails closed: if either role has no credential configured, we cannot prove
    the two families differ, so tailoring is refused.
    """
    rows = await conn.fetch(
        "SELECT provider, kind FROM credentials WHERE tenant_id = $1 AND kind = ANY($2::text[])",
        uuid.UUID(str(tenant_id)),
        sorted(TAILORING_ROLE_KINDS),
    )
    by_kind = {row["kind"]: row["provider"] for row in rows}

    tailor_provider = by_kind.get("tailor")
    verifier_provider = by_kind.get("verifier")
    if not tailor_provider or not verifier_provider:
        logger.warning(
            "cross_family_check_incomplete",
            tenant_id=tenant_id,
            tailor=tailor_provider,
            verifier=verifier_provider,
        )
        return True

    tailor_family = MODEL_FAMILIES.get(tailor_provider)
    verifier_family = MODEL_FAMILIES.get(verifier_provider)
    if not tailor_family or not verifier_family:
        logger.warning(
            "cross_family_unknown_provider",
            tenant_id=tenant_id,
            tailor=tailor_provider,
            verifier=verifier_provider,
        )
        return True

    return tailor_family == verifier_family
