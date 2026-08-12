"""Integration test for POST /api/jobs/{job_id}/generate-resume."""

import uuid

import httpx
import pytest

from jobos.api import main as api_main
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM jobs")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'acme-resume-test-%.example'")
    api_main.app.state.pool = db_pool
    yield
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM jobs")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'acme-resume-test-%.example'")


async def _client_and_token(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), token


async def test_generate_resume_for_unknown_job_returns_404(tenant_a_conn, tenant_a_id, db_pool):
    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.post(
            "/api/jobs/00000000-0000-0000-0000-000000000099/generate-resume",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 404


async def test_generate_resume_with_no_verified_bullets_returns_422(
    tenant_a_conn, tenant_a_id, db_pool
):
    company_id = await tenant_a_conn.fetchval(
        """
        INSERT INTO companies (id, name, domain) VALUES (gen_random_uuid(), 'Acme', $1)
        RETURNING id
        """,
        f"acme-resume-test-{uuid.uuid4().hex[:8]}.example",
    )
    job_id = await tenant_a_conn.fetchval(
        """
        INSERT INTO jobs (id, company_id, title, description, external_id)
        VALUES (gen_random_uuid(), $1, 'Engineer', 'Build things', 'ext-1')
        RETURNING id
        """,
        company_id,
    )

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.post(
            f"/api/jobs/{job_id}/generate-resume",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 422
