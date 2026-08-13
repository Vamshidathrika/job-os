"""Integration test: a warm contact at a company pulls an otherwise-marginal
job into Tier 1, while an identical job at a company with no warm contact
stays at Tier 2.

The test DB has no pre-seeded jobs (tests/conftest.py only seeds the two
fixed tenants), so this inserts its own company + job rows — see
tests/integration/test_matching_skill_coverage.py for the same pattern.

match_score is pinned via mocker so the test is not at the mercy of the
real embedder's cosine similarity, and ev_score is steered into the
0.40-0.60 band (the gap between the warm-contact bar and the standard bar)
by controlling years-of-experience through the number of distinct employers
in the Career Graph — see jobos/matcher/pipeline.py's
_years_of_experience/predict_salary_band and COMP_REFERENCE_INR/
DEFAULT_P_ACCEPT for the arithmetic this relies on:
    yoe = 3 companies * 2 = 6  ->  band p50 = INR 3,000,000 (3 <= yoe < 7)
    ev_score = min(1.0, 3,000,000 * 0.85 / 5,000,000) = 0.51
which is >= 0.40 (clears the warm-contact bar) and < 0.60 (fails the
standard bar), isolating has_warm_contact as the only thing that can move
match_score=0.55 into Tier 1.
"""

import uuid

import pytest

from jobos.db.models import EMBEDDING_DIM
from jobos.matcher.pipeline import run_matching

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

_PINNED_MATCH_SCORE = 0.55  # >= 0.50 (Tier 2 bar), < 0.65 (standard Tier 1 bar)


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs WHERE external_id LIKE 'warm-tiering-test-%'")
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'warm-tiering-test-%.example'")
    yield
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs WHERE external_id LIKE 'warm-tiering-test-%'")
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'warm-tiering-test-%.example'")


async def _seed_job(db_pool, company_name: str, external_id: str) -> uuid.UUID:
    async with db_pool.acquire() as conn:
        company_id = await conn.fetchval(
            "INSERT INTO companies (id, name, domain) VALUES (gen_random_uuid(), $1, $2) RETURNING id",
            company_name, f"warm-tiering-test-{uuid.uuid4().hex[:8]}.example",
        )
        job_id = await conn.fetchval(
            """
            INSERT INTO jobs (id, company_id, external_id, title, description, country, embedding)
            VALUES (gen_random_uuid(), $1, $2, 'Engineer', 'Python, Postgres', 'IN', $3::vector)
            RETURNING id
            """,
            company_id, external_id, str([0.01] * EMBEDDING_DIM),
        )
        return job_id


async def test_warm_contact_pulls_a_marginal_job_into_tier_1(tenant_a_conn, tenant_a_id, db_pool, mocker):
    # 3 distinct employers -> yoe=6 -> ev_score ~0.51, inside the
    # warm-contact-only band (>=0.40, <0.60).
    for company in ("Acme", "Globex", "Initech"):
        await tenant_a_conn.execute(
            "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
            "VALUES (gen_random_uuid(), $1::uuid, $2, 'Engineer', 'Built things in Python', 'verified')",
            tenant_a_id, company,
        )
    mocker.patch("jobos.matcher.pipeline.compute_similarity", return_value=_PINNED_MATCH_SCORE)

    warm_job_id = await _seed_job(db_pool, "Warmco", "warm-tiering-test-warm")
    cold_job_id = await _seed_job(db_pool, "Coldco", "warm-tiering-test-cold")

    # A real warm connection at Warmco only.
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, title, source) "
        "VALUES (gen_random_uuid(), $1::uuid, 'Warm Contact', 'Warmco', 'warm@example.com', "
        "'Engineer', 'linkedin_connection')",
        tenant_a_id,
    )

    counts = await run_matching(tenant_a_conn, str(tenant_a_id))
    assert counts["scored"] == 2

    warm_row = await tenant_a_conn.fetchrow(
        "SELECT score, ev_score, tier FROM matches WHERE user_id = $1::uuid AND job_id = $2",
        tenant_a_id, warm_job_id,
    )
    cold_row = await tenant_a_conn.fetchrow(
        "SELECT score, ev_score, tier FROM matches WHERE user_id = $1::uuid AND job_id = $2",
        tenant_a_id, cold_job_id,
    )
    assert warm_row is not None and cold_row is not None

    # Sanity: both jobs land in the ev_score band where has_warm_contact is
    # the only thing that can decide the tier.
    assert warm_row["score"] == pytest.approx(_PINNED_MATCH_SCORE)
    assert 0.40 <= warm_row["ev_score"] < 0.60
    assert cold_row["score"] == pytest.approx(_PINNED_MATCH_SCORE)
    assert 0.40 <= cold_row["ev_score"] < 0.60

    # The actual behavior under test: identical match/ev, but the job at the
    # company with a warm contact clears Tier 1 and the one without doesn't.
    assert warm_row["tier"] == 1, f"expected Warmco job in Tier 1, got {warm_row['tier']}"
    assert cold_row["tier"] == 2, f"expected Coldco job in Tier 2, got {cold_row['tier']}"


async def test_fuzzy_but_not_exact_company_match_does_not_grant_tier_1(
    tenant_a_conn, tenant_a_id, db_pool, mocker
):
    """A fuzzy company-name match that clears map_existing_network's general
    FUZZY_MATCH_THRESHOLD (0.5) but is not an exact core-name match must NOT
    set has_warm_contact for tiering purposes.

    Before this, a fuzzy false positive in warm-contact matching could
    incorrectly promote a job to Tier 1 and defer a cold application by up
    to 7 days waiting on a referral that doesn't actually exist. Fuzzy
    matching stays fine for jobos/runner/warm_paths.py's outreach-discovery
    use (a bad candidate there just gets filtered out later) — this test is
    specifically about the tiering signal computed in
    jobos/matcher/pipeline.py.

    "Acme" (contact company) vs "Acme Bank" (job company) is Jaccard 0.5 —
    it clears the general threshold but is not an exact core-name match, so
    it must not grant Tier 1. "Globex" (contact company) vs "Globex" (job
    company) is an exact match and must grant Tier 1.
    """
    for company in ("Acme", "Globex", "Initech"):
        await tenant_a_conn.execute(
            "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
            "VALUES (gen_random_uuid(), $1::uuid, $2, 'Engineer', 'Built things in Python', 'verified')",
            tenant_a_id, company,
        )
    mocker.patch("jobos.matcher.pipeline.compute_similarity", return_value=_PINNED_MATCH_SCORE)

    fuzzy_job_id = await _seed_job(db_pool, "Acme Bank", "warm-tiering-test-fuzzy")
    exact_job_id = await _seed_job(db_pool, "Globex", "warm-tiering-test-exact")

    # A contact whose company name only fuzzy-matches the job's company.
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, title, source) "
        "VALUES (gen_random_uuid(), $1::uuid, 'Fuzzy Contact', 'Acme', 'fuzzy@example.com', "
        "'Engineer', 'linkedin_connection')",
        tenant_a_id,
    )
    # A contact whose company name exactly matches the job's company.
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, title, source) "
        "VALUES (gen_random_uuid(), $1::uuid, 'Exact Contact', 'Globex', 'exact@example.com', "
        "'Engineer', 'linkedin_connection')",
        tenant_a_id,
    )

    counts = await run_matching(tenant_a_conn, str(tenant_a_id))
    assert counts["scored"] == 2

    fuzzy_row = await tenant_a_conn.fetchrow(
        "SELECT ev_score, tier FROM matches WHERE user_id = $1::uuid AND job_id = $2",
        tenant_a_id, fuzzy_job_id,
    )
    exact_row = await tenant_a_conn.fetchrow(
        "SELECT ev_score, tier FROM matches WHERE user_id = $1::uuid AND job_id = $2",
        tenant_a_id, exact_job_id,
    )
    assert fuzzy_row is not None and exact_row is not None

    # Sanity: both jobs land in the ev_score band where has_warm_contact is
    # the only thing that can decide the tier.
    assert 0.40 <= fuzzy_row["ev_score"] < 0.60
    assert 0.40 <= exact_row["ev_score"] < 0.60

    assert fuzzy_row["tier"] == 2, (
        f"fuzzy-only company match must not grant Tier 1, got {fuzzy_row['tier']}"
    )
    assert exact_row["tier"] == 1, (
        f"exact company match must grant Tier 1, got {exact_row['tier']}"
    )
