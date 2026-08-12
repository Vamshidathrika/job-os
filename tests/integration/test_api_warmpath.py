"""Integration tests for GET /api/warmpath/status and GET /api/warmpath/races.

/api/warmpath/status is NOT backed by warm_path_races — its own docstring in
jobos/api/main.py says so explicitly: "Not backed by any specific job's real
race ... days_elapsed and warm_responses are accepted as explicit inputs
precisely so this cannot silently pretend to know a real race's progress."
It also has no Depends() at all, so seeding a warm_path_races row would both
have zero effect on its response and be testing a claim the code disavows.
Instead this asserts the response matches calling should_hold_application /
select_fallback_band directly with the same inputs.

/api/warmpath/races IS backed by the real table and IS behind
authenticated_tenant, so that's where the seeded-row assertion and the 401
check for this file live.
"""

import uuid

import httpx
import pytest

from jobos.api import main as api_main
from jobos.vault.api_tokens import create_token
from jobos.warm_path.decision import select_fallback_band, should_hold_application

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _client(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _client_and_token(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")
    return await _client(db_pool), token


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM warm_path_races")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs WHERE external_id LIKE 'warmpath-test-%'")
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'warmpath-test-%.example'")
    api_main.app.state.pool = db_pool
    yield
    await tenant_a_conn.execute("DELETE FROM warm_path_races")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs WHERE external_id LIKE 'warmpath-test-%'")
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'warmpath-test-%.example'")


@pytest.mark.parametrize(
    "tier,match_score,ev_score,days_elapsed,warm_responses",
    [
        (1, 0.9, 69300.0, 0, 0),
        (2, 0.5, 10000.0, 3, 0),
        (1, 0.9, 69300.0, 7, 0),
        (1, 0.9, 69300.0, 2, 1),
    ],
)
async def test_status_matches_the_decision_functions_directly(
    db_pool, tier, match_score, ev_score, days_elapsed, warm_responses
):
    expected = {
        "tier": tier,
        "hold_for_warm_path": should_hold_application(match_score, ev_score, tier),
        "current_fallback_band": select_fallback_band(days_elapsed, warm_responses),
    }

    async with await _client(db_pool) as client:
        response = await client.get(
            "/api/warmpath/status",
            params={
                "tier": tier,
                "match_score": match_score,
                "ev_score": ev_score,
                "days_elapsed": days_elapsed,
                "warm_responses": warm_responses,
            },
        )

    assert response.status_code == 200
    assert response.json() == expected


async def test_list_races_returns_a_real_seeded_row(tenant_a_conn, tenant_a_id, db_pool):
    suffix = uuid.uuid4().hex[:8]
    company_id = await tenant_a_conn.fetchval(
        "INSERT INTO companies (id, name, domain) VALUES (gen_random_uuid(), 'Stripe Clone', $1) RETURNING id",
        f"warmpath-test-{suffix}.example",
    )
    job_id = await tenant_a_conn.fetchval(
        """
        INSERT INTO jobs (id, company_id, external_id, title)
        VALUES (gen_random_uuid(), $1, $2, 'Staff AI Engineer')
        RETURNING id
        """,
        company_id,
        f"warmpath-test-{suffix}",
    )
    await tenant_a_conn.execute(
        """
        INSERT INTO warm_path_races (user_id, job_id, status, channels, deadline_at)
        VALUES ($1, $2, 'running', '{email}', now() + interval '4 days')
        """,
        tenant_a_id,
        job_id,
    )

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.get(
            "/api/warmpath/races", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    race = body[0]
    # The old dashboard hardcoded exactly this fictional race — assert the
    # real seeded row instead, not that fixed string.
    assert race["company"] == "Stripe Clone"
    assert race["title"] == "Staff AI Engineer"
    assert race["status"] == "running"
    assert race["responded_channel"] is None
    assert race["resolution"] is None
    assert race["started_at"] is not None
    assert race["deadline_at"] is not None


async def test_list_races_without_a_token_is_rejected(db_pool):
    async with await _client(db_pool) as client:
        response = await client.get("/api/warmpath/races")
    assert response.status_code == 401
