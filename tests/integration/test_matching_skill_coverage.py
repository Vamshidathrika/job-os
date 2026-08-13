"""Integration test for skill-coverage scoring in run_matching.

The test DB has no pre-seeded jobs (tests/conftest.py only seeds the two
fixed tenants), so this inserts its own company + job row rather than
relying on one existing — see tests/integration/test_generate_resume_endpoint.py
for the same insert pattern.
"""

import uuid

import pytest

from jobos.matcher.pipeline import run_matching

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM job_requirements")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs WHERE external_id LIKE 'skill-coverage-test-%'")
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'skill-coverage-test-%.example'")
    yield
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM job_requirements")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs WHERE external_id LIKE 'skill-coverage-test-%'")
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'skill-coverage-test-%.example'")


async def test_run_matching_persists_skill_coverage(tenant_a_conn, tenant_a_id, db_pool):
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1::uuid, 'Acme', 'Engineer', 'Built things with Python and PostgreSQL', 'verified')",
        tenant_a_id,
    )

    async with db_pool.acquire() as conn:
        company_id = await conn.fetchval(
            "INSERT INTO companies (id, name, domain) VALUES (gen_random_uuid(), 'Acme', $1) RETURNING id",
            f"skill-coverage-test-{uuid.uuid4().hex[:8]}.example",
        )
        job_id = await conn.fetchval(
            """
            INSERT INTO jobs (id, company_id, title, description, external_id, embedding)
            VALUES (
                gen_random_uuid(), $1, 'Engineer', 'Needs Python, PostgreSQL, Kubernetes',
                'skill-coverage-test-1', (SELECT array_fill(0.1, ARRAY[384])::vector)
            )
            RETURNING id
            """,
            company_id,
        )

    await tenant_a_conn.execute(
        "INSERT INTO job_requirements (job_id, hard_reqs) VALUES ($1, $2::jsonb) "
        "ON CONFLICT (job_id) DO UPDATE SET hard_reqs = EXCLUDED.hard_reqs",
        job_id, '["Python", "PostgreSQL", "Kubernetes"]',
    )

    await run_matching(tenant_a_conn, str(tenant_a_id))

    row = await tenant_a_conn.fetchrow(
        "SELECT skill_coverage, missing_skills FROM matches WHERE user_id = $1::uuid AND job_id = $2",
        tenant_a_id, job_id,
    )
    assert row is not None
    assert row["skill_coverage"] == pytest.approx(2 / 3)
    assert "Kubernetes" in row["missing_skills"]
