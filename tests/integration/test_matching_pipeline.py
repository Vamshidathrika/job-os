"""Integration tests for the matching pipeline."""

import uuid

import pytest

from jobos.db.models import EMBEDDING_DIM
from jobos.matcher.pipeline import build_profile_text, run_matching

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")
    yield
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")


async def _seed_job(db_pool, title: str, description: str) -> uuid.UUID:
    async with db_pool.acquire() as conn:
        company_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO companies (id, name, domain) VALUES ($1, $2, $3)",
            company_id, "Acme", f"acme-{company_id.hex[:8]}.example",
        )
        job_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO jobs (id, company_id, external_id, title, description, country, embedding) "
            "VALUES ($1, $2, $3, $4, $5, 'IN', $6::vector)",
            job_id, company_id, f"ext-{job_id.hex[:6]}", title, description,
            str([0.01] * EMBEDDING_DIM),
        )
        return job_id


async def test_matching_writes_scored_rows(tenant_a_conn, tenant_a_id, db_pool):
    job_id = await _seed_job(db_pool, "Backend Engineer", "Python, Postgres, caching")
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Acme', 'Backend Engineer', 'Built Redis caches in Python', 'verified')",
        tenant_a_id,
    )

    counts = await run_matching(tenant_a_conn, str(tenant_a_id))

    assert counts["scored"] == 1
    row = await tenant_a_conn.fetchrow(
        "SELECT job_id, score, ev_score, tier FROM matches WHERE job_id = $1", job_id
    )
    assert row is not None
    assert 0.0 <= row["score"] <= 1.0
    assert row["ev_score"] > 0
    assert row["tier"] in (1, 2, 3)


async def test_matching_is_idempotent(tenant_a_conn, tenant_a_id, db_pool):
    await _seed_job(db_pool, "Backend Engineer", "Python")
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Acme', 'Engineer', 'Built things in Python', 'verified')",
        tenant_a_id,
    )

    await run_matching(tenant_a_conn, str(tenant_a_id))
    await run_matching(tenant_a_conn, str(tenant_a_id))

    assert await tenant_a_conn.fetchval("SELECT count(*) FROM matches") == 1


async def test_no_profile_scores_nothing(tenant_a_conn, tenant_a_id, db_pool):
    """With no career history there is nothing to match against."""
    await _seed_job(db_pool, "Backend Engineer", "Python")

    counts = await run_matching(tenant_a_conn, str(tenant_a_id))

    assert counts["scored"] == 0


async def test_profile_text_uses_the_career_graph():
    bullets = [
        {"bullet_text": "Built Redis caches", "role": "Backend Engineer", "company": "Acme"},
        {"bullet_text": "Led a team of 4", "role": "Backend Engineer", "company": "Acme"},
    ]
    text = build_profile_text(bullets)

    assert "Redis" in text
    assert "Backend Engineer" in text


async def test_matches_are_tenant_isolated(tenant_a_conn, tenant_b_conn, tenant_a_id, db_pool):
    await _seed_job(db_pool, "Backend Engineer", "Python")
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Acme', 'Engineer', 'Built things in Python', 'verified')",
        tenant_a_id,
    )
    await run_matching(tenant_a_conn, str(tenant_a_id))

    assert await tenant_b_conn.fetchval("SELECT count(*) FROM matches") == 0


async def test_tier_1_is_reachable_for_a_strong_senior_match(tenant_a_conn, tenant_a_id, db_pool, mocker):
    """Regression: ev_score must be able to clear the Tier-1 gate.

    classify_tier requires match_score >= 0.65 AND ev_score >= 0.60. An
    earlier version computed ev_score from p_offer (itself derived from
    match_score and damped by 0.35), so ev_score could never exceed 0.35 —
    Tier 1 was unreachable and the 7-day warm-path race, which only fires on
    Tier 1, could never start for any job.
    """
    job_id = await _seed_job(db_pool, "Senior Backend Engineer", "Python, Postgres, Redis caching")
    # A senior profile: several employers, so the comp band is senior.
    for company in ("Acme", "Globex", "Initech", "Umbrella"):
        await tenant_a_conn.execute(
            "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
            "VALUES (gen_random_uuid(), $1, $2, 'Senior Backend Engineer', "
            "'Built Python services on Postgres with Redis caching at scale', 'verified')",
            tenant_a_id, company,
        )
    # Pin similarity high: this test is about the EV scale, not the embedder.
    mocker.patch("jobos.matcher.pipeline.compute_similarity", return_value=0.9)

    await run_matching(tenant_a_conn, str(tenant_a_id))

    row = await tenant_a_conn.fetchrow(
        "SELECT score, ev_score, tier FROM matches WHERE job_id = $1", job_id
    )
    assert row["score"] >= 0.65
    assert row["ev_score"] >= 0.60, (
        f"ev_score {row['ev_score']} cannot clear the 0.60 Tier-1 gate"
    )
    assert row["tier"] == 1
