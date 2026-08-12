"""Integration tests for API authentication.

The property under test: a caller cannot choose which tenant they act as.
Before this landed, `X-Tenant-Id: <any uuid>` was sufficient to read and
write that tenant's rows, including their stored credentials.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from jobos.api.main import app
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
async def client(db_pool, setup_schema):
    """An HTTP client wired to the real app against the test database."""
    app.state.pool = db_pool
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture(autouse=True)
async def clean(db_pool, setup_schema):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM api_tokens")
        await conn.execute("DELETE FROM auth_failures")
    yield
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM api_tokens")
        await conn.execute("DELETE FROM auth_failures")


@pytest.fixture
async def token_a(db_pool, tenant_a_id) -> str:
    async with db_pool.acquire() as conn:
        return await create_token(conn, str(tenant_a_id), name="test")


async def test_request_without_a_token_is_rejected(client):
    response = await client.get("/api/stats")
    assert response.status_code == 401


async def test_asserting_a_tenant_id_header_grants_nothing(client, tenant_a_id):
    """The old bypass: claiming a tenant used to be enough to act as them."""
    response = await client.get("/api/stats", headers={"X-Tenant-Id": str(tenant_a_id)})
    assert response.status_code == 401


async def test_valid_token_is_accepted(client, token_a):
    response = await client.get("/api/stats", headers={"Authorization": f"Bearer {token_a}"})

    assert response.status_code == 200
    assert "jobs_tracked" in response.json()


async def test_garbage_token_is_rejected(client):
    for value in ("Bearer nonsense", "Bearer jobos_wrong", "nonsense", "Bearer "):
        response = await client.get("/api/stats", headers={"Authorization": value})
        assert response.status_code == 401, f"accepted bad credential: {value!r}"


async def test_revoked_token_is_rejected(client, db_pool, tenant_a_id, token_a):
    from jobos.vault.api_tokens import revoke_token

    async with db_pool.acquire() as conn:
        await revoke_token(conn, str(tenant_a_id), name="test")

    response = await client.get("/api/stats", headers={"Authorization": f"Bearer {token_a}"})
    assert response.status_code == 401


async def test_token_cannot_be_overridden_by_a_header(client, db_pool, token_a, tenant_b_id):
    """Presenting tenant A's token while claiming to be tenant B must act as A."""
    response = await client.get(
        "/api/security/status",
        headers={"Authorization": f"Bearer {token_a}", "X-Tenant-Id": str(tenant_b_id)},
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] != str(tenant_b_id)


async def test_health_stays_public(client):
    """Liveness probes must not need a credential."""
    response = await client.get("/health")
    assert response.status_code == 200


async def test_repeated_failed_auth_attempts_get_rate_limited(client):
    """5 bad tokens each fail normally; the 6th is blocked before it is even checked."""
    for _ in range(5):
        response = await client.get(
            "/api/stats", headers={"Authorization": "Bearer jobos_wrong-token"}
        )
        assert response.status_code == 401

    response = await client.get(
        "/api/stats", headers={"Authorization": "Bearer jobos_wrong-token"}
    )
    assert response.status_code == 429


async def test_rate_limit_blocks_a_valid_token_once_tripped(client, token_a):
    """Once the IP is over the limit, even a real token is refused outright."""
    for _ in range(5):
        await client.get("/api/stats", headers={"Authorization": "Bearer jobos_wrong-token"})

    response = await client.get("/api/stats", headers={"Authorization": f"Bearer {token_a}"})
    assert response.status_code == 429
