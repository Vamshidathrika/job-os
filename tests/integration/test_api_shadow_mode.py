"""Integration tests for GET /api/shadow-mode and POST /api/shadow-mode."""

import httpx
import pytest

from jobos.api import main as api_main
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, tenant_a_id, db_pool):
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    await tenant_a_conn.execute(
        "UPDATE tenants SET autonomy_mode = 'shadow' WHERE id = $1", tenant_a_id
    )
    api_main.app.state.pool = db_pool
    yield
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    await tenant_a_conn.execute(
        "UPDATE tenants SET autonomy_mode = 'shadow' WHERE id = $1", tenant_a_id
    )


async def _client_and_token(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), token


async def test_get_shadow_mode_reflects_real_tenant_row(tenant_a_conn, tenant_a_id, db_pool):
    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.get(
            "/api/shadow-mode", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.json() == {"enabled": True}

    await tenant_a_conn.execute(
        "UPDATE tenants SET autonomy_mode = 'autopilot' WHERE id = $1", tenant_a_id
    )

    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client2:
        response2 = await client2.get(
            "/api/shadow-mode", headers={"Authorization": f"Bearer {token}"}
        )
    assert response2.json() == {"enabled": False}


async def test_post_shadow_mode_actually_flips_the_tenants_row(
    tenant_a_conn, tenant_a_id, db_pool
):
    """The old dashboard toggle was pure client state and changed nothing
    real. Assert against tenants.autonomy_mode directly, not just the
    response body echoing back what was sent."""
    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.post(
            "/api/shadow-mode",
            params={"enabled": "false"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == {"enabled": False}

    mode = await tenant_a_conn.fetchval(
        "SELECT autonomy_mode FROM tenants WHERE id = $1", tenant_a_id
    )
    assert mode == "autopilot"

    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client2:
        response2 = await client2.post(
            "/api/shadow-mode",
            params={"enabled": "true"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response2.json() == {"enabled": True}
    mode2 = await tenant_a_conn.fetchval(
        "SELECT autonomy_mode FROM tenants WHERE id = $1", tenant_a_id
    )
    assert mode2 == "shadow"


async def test_shadow_mode_without_a_token_is_rejected(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/shadow-mode")
    assert response.status_code == 401
