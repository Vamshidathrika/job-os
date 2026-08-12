"""Integration tests for API token authentication.

Tenant identity must come from a secret the caller proves they hold, never
from a header they simply assert. These tests pin that property.
"""

import pytest

from jobos.vault.api_tokens import (
    TOKEN_PREFIX,
    InvalidTokenError,
    create_token,
    list_tokens,
    resolve_tenant,
    revoke_token,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(db_pool, setup_schema):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM api_tokens")
        await conn.execute("DELETE FROM api_token_audit")
    yield
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM api_tokens")
        await conn.execute("DELETE FROM api_token_audit")


async def test_created_token_resolves_to_its_tenant(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="laptop")

        assert token.startswith(TOKEN_PREFIX)
        assert await resolve_tenant(conn, token) == str(tenant_a_id)


async def test_plaintext_token_is_never_stored(db_pool, tenant_a_id):
    """A leaked database dump must not yield working credentials."""
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="laptop")

        row = await conn.fetchrow("SELECT token_hash, name FROM api_tokens")
        assert token not in row["token_hash"]
        # The secret half must not appear anywhere in the row.
        secret = token[len(TOKEN_PREFIX) :]
        assert secret not in str(dict(row))


async def test_unknown_token_is_rejected(db_pool):
    async with db_pool.acquire() as conn:
        with pytest.raises(InvalidTokenError):
            await resolve_tenant(conn, f"{TOKEN_PREFIX}not-a-real-token")


async def test_garbage_input_is_rejected(db_pool):
    async with db_pool.acquire() as conn:
        for bad in ("", "   ", "Bearer something", "jobos_"):
            with pytest.raises(InvalidTokenError):
                await resolve_tenant(conn, bad)


async def test_revoked_token_stops_working_immediately(db_pool, tenant_a_id):
    """Revocation is the whole reason these are opaque rather than JWTs."""
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="laptop")
        assert await resolve_tenant(conn, token) == str(tenant_a_id)

        await revoke_token(conn, str(tenant_a_id), name="laptop")

        with pytest.raises(InvalidTokenError):
            await resolve_tenant(conn, token)


async def test_two_tenants_tokens_do_not_cross(db_pool, tenant_a_id, tenant_b_id):
    async with db_pool.acquire() as conn:
        token_a = await create_token(conn, str(tenant_a_id), name="a")
        token_b = await create_token(conn, str(tenant_b_id), name="b")

        assert await resolve_tenant(conn, token_a) == str(tenant_a_id)
        assert await resolve_tenant(conn, token_b) == str(tenant_b_id)
        assert token_a != token_b


async def test_tokens_are_unpredictable(db_pool, tenant_a_id):
    """Sequential or low-entropy tokens would be guessable."""
    async with db_pool.acquire() as conn:
        tokens = {await create_token(conn, str(tenant_a_id), name=f"t{i}") for i in range(5)}

    assert len(tokens) == 5
    secrets = [t[len(TOKEN_PREFIX) :] for t in tokens]
    assert all(len(s) >= 32 for s in secrets), "token secret is too short to resist guessing"


async def test_listing_tokens_never_exposes_the_secret(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="laptop")

        listed = await list_tokens(conn, str(tenant_a_id))

    assert len(listed) == 1
    assert listed[0]["name"] == "laptop"
    assert token not in str(listed)


async def test_resolving_records_last_used(db_pool, tenant_a_id):
    """Dormant or leaked tokens are only findable if use is recorded."""
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="laptop")
        assert (await list_tokens(conn, str(tenant_a_id)))[0]["last_used_at"] is None

        await resolve_tenant(conn, token)

        assert (await list_tokens(conn, str(tenant_a_id)))[0]["last_used_at"] is not None


async def test_expired_token_is_rejected(db_pool, tenant_a_id):
    """An already-expired token must fail exactly like an unknown/revoked one."""
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="laptop", expires_in_days=-1)

        with pytest.raises(InvalidTokenError):
            await resolve_tenant(conn, token)


async def test_token_with_no_expiry_still_resolves(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="laptop", expires_in_days=None)

        assert await resolve_tenant(conn, token) == str(tenant_a_id)


async def test_token_with_future_expiry_still_resolves(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="laptop", expires_in_days=30)

        assert await resolve_tenant(conn, token) == str(tenant_a_id)


async def test_resolve_tenant_audits_success_and_failure(db_pool, tenant_a_id):
    """Every authentication attempt leaves a trail beyond just last_used_at."""
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="laptop")

        await resolve_tenant(conn, token)
        with pytest.raises(InvalidTokenError):
            await resolve_tenant(conn, f"{TOKEN_PREFIX}not-a-real-token")

        rows = await conn.fetch("SELECT success, user_id FROM api_token_audit")

    assert len(rows) == 2
    success_row = next(r for r in rows if r["success"])
    failure_row = next(r for r in rows if not r["success"])
    assert success_row["user_id"] == tenant_a_id
    assert failure_row["user_id"] is None
