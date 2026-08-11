"""Integration tests wiring Tier-1 matches into warm-path races."""

import json
import uuid

import pytest

from jobos.runner.warm_paths import start_races_for_tier_1

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _sequence_reply() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        [
                            {"subject": "s1", "body": "b1"},
                            {"subject": "s2", "body": "b2"},
                            {"subject": "s3", "body": "b3"},
                        ]
                    )
                }
            }
        ]
    }


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    for table in ("warm_path_races", "action_queue", "matches", "people"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")
    yield
    for table in ("warm_path_races", "action_queue", "matches", "people"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")


async def _tier_1_job(tenant_a_conn, tenant_a_id, db_pool, company_name="Globex") -> uuid.UUID:
    async with db_pool.acquire() as conn:
        company_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO companies (id, name, domain) VALUES ($1, $2, $3)",
            company_id, company_name, f"{company_name.lower()}.example",
        )
        job_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO jobs (id, company_id, external_id, title) VALUES ($1, $2, $3, $4)",
            job_id, company_id, f"ext-{job_id.hex[:6]}", "Backend Engineer",
        )
    await tenant_a_conn.execute(
        "INSERT INTO matches (id, user_id, job_id, score, ev_score, tier) "
        "VALUES (gen_random_uuid(), $1, $2, 0.8, 0.7, 1)",
        tenant_a_id, job_id,
    )
    return job_id


async def test_race_starts_when_a_connection_works_there(
    tenant_a_conn, tenant_a_id, db_pool, mocker
):
    mocker.patch("jobos.referral.sequence.acompletion", return_value=_sequence_reply())
    job_id = await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, source) "
        "VALUES (gen_random_uuid(), $1, 'Ravi Kumar', 'Globex', 'ravi@globex.example', 'linkedin_connection')",
        tenant_a_id,
    )

    counts = await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    assert counts["started"] == 1
    race = await tenant_a_conn.fetchrow(
        "SELECT status FROM warm_path_races WHERE job_id = $1", job_id
    )
    assert race["status"] == "running"
    touches = await tenant_a_conn.fetchval(
        "SELECT count(*) FROM action_queue WHERE action_type = 'referral_touch'"
    )
    assert touches == 3


async def test_no_connection_means_no_race(tenant_a_conn, tenant_a_id, db_pool):
    """A job where the operator knows nobody must be recorded, not silently skipped."""
    await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)

    counts = await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    assert counts["started"] == 0
    assert counts["no_warm_path"] == 1
    assert await tenant_a_conn.fetchval("SELECT count(*) FROM warm_path_races") == 0


async def test_only_tier_1_jobs_race(tenant_a_conn, tenant_a_id, db_pool, mocker):
    mocker.patch("jobos.referral.sequence.acompletion", return_value=_sequence_reply())
    job_id = await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)
    await tenant_a_conn.execute("UPDATE matches SET tier = 2 WHERE job_id = $1", job_id)

    counts = await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    assert counts["started"] == 0
    assert await tenant_a_conn.fetchval("SELECT count(*) FROM warm_path_races") == 0


async def test_gated_when_no_shared_context(tenant_a_conn, tenant_a_id, db_pool, mocker):
    """The personalisation gate drops contacts with no real common ground."""
    llm = mocker.patch("jobos.referral.sequence.acompletion")
    await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, source) "
        "VALUES (gen_random_uuid(), $1, 'Stranger Person', 'Globex', 's@globex.example', 'apollo')",
        tenant_a_id,
    )

    counts = await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    assert counts["gated"] == 1
    assert counts["started"] == 0
    llm.assert_not_called()


async def test_rerun_does_not_duplicate_touches(tenant_a_conn, tenant_a_id, db_pool, mocker):
    mocker.patch("jobos.referral.sequence.acompletion", return_value=_sequence_reply())
    await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, source) "
        "VALUES (gen_random_uuid(), $1, 'Ravi Kumar', 'Globex', 'ravi@globex.example', 'linkedin_connection')",
        tenant_a_id,
    )

    await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))
    await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    touches = await tenant_a_conn.fetchval(
        "SELECT count(*) FROM action_queue WHERE action_type = 'referral_touch'"
    )
    assert touches == 3, "an already-running race must not be restarted"
