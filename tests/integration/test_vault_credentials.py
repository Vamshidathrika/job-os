"""Integration tests for credential storage against the real database.

These exercise the encrypt -> persist -> fetch -> decrypt round trip under
RLS, plus the cross-family entailment gate that decides whether autonomous
tailoring is permitted.
"""

import uuid

import pytest

from jobos.vault.credentials import (
    CredentialNotFoundError,
    check_cross_family,
    mark_validation_result,
    retrieve_credential,
    store_credential,
)
from jobos.vault.encryption import generate_dek

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean_credentials(tenant_a_conn, tenant_b_conn):
    """Credentials are keyed per (tenant, provider) and persist across tests,
    so each test must start from a known-empty vault for both tenants."""
    for conn in (tenant_a_conn, tenant_b_conn):
        await conn.execute("DELETE FROM credentials")
    yield
    for conn in (tenant_a_conn, tenant_b_conn):
        await conn.execute("DELETE FROM credentials")


async def test_store_then_retrieve_round_trips_plaintext(tenant_a_conn, tenant_a_id, sample_credential):
    dek = generate_dek()
    await store_credential(
        tenant_a_conn, str(tenant_a_id), "groq", "tailor", sample_credential, dek
    )

    recovered = await retrieve_credential(tenant_a_conn, str(tenant_a_id), "groq", dek)
    assert recovered == sample_credential


async def test_plaintext_is_never_persisted(tenant_a_conn, tenant_a_id, sample_credential):
    dek = generate_dek()
    await store_credential(
        tenant_a_conn, str(tenant_a_id), "openrouter", "tailor", sample_credential, dek
    )

    row = await tenant_a_conn.fetchrow(
        "SELECT ciphertext, nonce, last4 FROM credentials WHERE tenant_id = $1 AND provider = $2",
        tenant_a_id,
        "openrouter",
    )
    assert sample_credential.encode() not in bytes(row["ciphertext"])
    assert row["last4"] == sample_credential[-4:]
    assert len(bytes(row["nonce"])) == 12


async def test_retrieve_missing_credential_raises(tenant_a_conn, tenant_a_id):
    with pytest.raises(CredentialNotFoundError):
        await retrieve_credential(tenant_a_conn, str(tenant_a_id), "icypeas", generate_dek())


async def test_wrong_dek_cannot_decrypt(tenant_a_conn, tenant_a_id, sample_credential):
    await store_credential(
        tenant_a_conn, str(tenant_a_id), "apollo", "enrichment", sample_credential, generate_dek()
    )
    with pytest.raises(Exception):
        await retrieve_credential(tenant_a_conn, str(tenant_a_id), "apollo", generate_dek())


async def test_store_is_idempotent_per_provider(tenant_a_conn, tenant_a_id):
    dek = generate_dek()
    await store_credential(tenant_a_conn, str(tenant_a_id), "cloudflare", "embedding", "key-one", dek)
    await store_credential(tenant_a_conn, str(tenant_a_id), "cloudflare", "embedding", "key-two", dek)

    count = await tenant_a_conn.fetchval(
        "SELECT count(*) FROM credentials WHERE tenant_id = $1 AND provider = $2",
        tenant_a_id,
        "cloudflare",
    )
    assert count == 1
    assert await retrieve_credential(tenant_a_conn, str(tenant_a_id), "cloudflare", dek) == "key-two"


async def test_revalidation_resets_status_on_rotation(tenant_a_conn, tenant_a_id):
    dek = generate_dek()
    await store_credential(tenant_a_conn, str(tenant_a_id), "linkedin", "social", "token-one", dek)
    await mark_validation_result(tenant_a_conn, str(tenant_a_id), "linkedin", True)
    assert await _status(tenant_a_conn, tenant_a_id, "linkedin") == "valid"

    # Rotating the key must invalidate the previous "valid" verdict.
    await store_credential(tenant_a_conn, str(tenant_a_id), "linkedin", "social", "token-two", dek)
    assert await _status(tenant_a_conn, tenant_a_id, "linkedin") == "unvalidated"


async def test_cross_family_fails_closed_when_roles_missing(tenant_b_conn, tenant_b_id):
    """No tailor/verifier configured -> must refuse (return True)."""
    assert await check_cross_family(tenant_b_conn, str(tenant_b_id)) is True


async def test_cross_family_detects_same_family(tenant_b_conn, tenant_b_id):
    dek = generate_dek()
    # groq and nim are both the 'llama' family -> tailoring must be refused.
    await store_credential(tenant_b_conn, str(tenant_b_id), "groq", "tailor", "k1", dek)
    await store_credential(tenant_b_conn, str(tenant_b_id), "nim", "verifier", "k2", dek)

    assert await check_cross_family(tenant_b_conn, str(tenant_b_id)) is True


async def test_cross_family_allows_distinct_families(tenant_b_conn, tenant_b_id):
    dek = generate_dek()
    # openrouter ('mixed') vs nim ('llama') -> distinct, tailoring permitted.
    await store_credential(tenant_b_conn, str(tenant_b_id), "openrouter", "tailor", "k1", dek)
    await store_credential(tenant_b_conn, str(tenant_b_id), "nim", "verifier", "k2", dek)

    assert await check_cross_family(tenant_b_conn, str(tenant_b_id)) is False


async def _status(conn, tenant_id: uuid.UUID, provider: str) -> str:
    return await conn.fetchval(
        "SELECT status FROM credentials WHERE tenant_id = $1 AND provider = $2",
        tenant_id,
        provider,
    )
