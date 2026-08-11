"""End-to-end smoke test: the whole pipeline in one run."""

import json

import pytest

from jobos.config import Settings
from jobos.runner.pipeline import run_full_pipeline

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 4242,
            "title": "Backend Engineer",
            "location": {"name": "Bengaluru, India"},
            "content": "Python, Postgres and caching at scale.",
        }
    ]
}


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    for table in ("warm_path_races", "action_queue", "matches", "people", "cg_bullets"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")
    yield


async def test_full_pipeline_produces_matches(tenant_a_conn, tenant_a_id, db_pool, tmp_path, mocker):
    mocker.patch(
        "jobos.ingestion.poller.ATSPoller._fetch_with_retry", return_value=GREENHOUSE_PAYLOAD
    )
    mocker.patch(
        "jobos.referral.sequence.acompletion",
        return_value={"choices": [{"message": {"content": json.dumps([
            {"subject": "s1", "body": "b1"},
            {"subject": "s2", "body": "b2"},
            {"subject": "s3", "body": "b3"},
        ])}}]},
    )

    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "companies:\n"
        "  - name: Acme\n"
        "    domain: acme.example\n"
        "    ats_type: greenhouse\n"
        "    ats_identifier: acme\n"
    )

    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Prior Co', 'Backend Engineer', "
        "'Built Python services on Postgres with Redis caching', 'verified')",
        tenant_a_id,
    )

    result = await run_full_pipeline(
        db_pool, str(tenant_a_id), Settings(), seed_path=str(seed)
    )

    assert result["seed"]["inserted"] == 1
    assert result["ingest"]["ingested"] == 1
    assert result["match"]["scored"] == 1

    job_count = await tenant_a_conn.fetchval("SELECT count(*) FROM matches")
    assert job_count == 1


async def test_pipeline_is_idempotent(tenant_a_conn, tenant_a_id, db_pool, tmp_path, mocker):
    mocker.patch(
        "jobos.ingestion.poller.ATSPoller._fetch_with_retry", return_value=GREENHOUSE_PAYLOAD
    )
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "companies:\n  - name: Acme\n    domain: acme.example\n"
        "    ats_type: greenhouse\n    ats_identifier: acme\n"
    )
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Prior Co', 'Engineer', 'Built Python services', 'verified')",
        tenant_a_id,
    )

    await run_full_pipeline(db_pool, str(tenant_a_id), Settings(), seed_path=str(seed))
    await run_full_pipeline(db_pool, str(tenant_a_id), Settings(), seed_path=str(seed))

    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM jobs") == 1
    assert await tenant_a_conn.fetchval("SELECT count(*) FROM matches") == 1
