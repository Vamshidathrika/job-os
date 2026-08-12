"""Integration tests for GET /api/jobs and GET /api/radar/signals."""

import uuid

import httpx
import pytest

from jobos.api import main as api_main
from jobos.hiring_radar.sources import scan_funding_rss
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

FUNDING_XML = """<?xml version="1.0"?>
<rss><channel>
<item>
<title>Acme raises $50M Series B</title>
<description>Acme announced a new funding round led by Sequoia.</description>
</item>
<item>
<title>Unrelated hiring news</title>
<description>Nothing about money here.</description>
</item>
</channel></rss>"""


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs WHERE external_id LIKE 'radar-test-%'")
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'jobs-radar-test-%.example'")
    api_main.app.state.pool = db_pool
    yield
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs WHERE external_id LIKE 'radar-test-%'")
        await conn.execute("DELETE FROM companies WHERE domain LIKE 'jobs-radar-test-%.example'")


async def _client_and_token(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), token


async def test_list_jobs_returns_real_rows_with_and_without_a_match(
    tenant_a_conn, tenant_a_id, db_pool
):
    suffix = uuid.uuid4().hex[:8]
    domain = f"jobs-radar-test-{suffix}.example"
    company_id = await tenant_a_conn.fetchval(
        "INSERT INTO companies (id, name, domain) VALUES (gen_random_uuid(), 'Acme Radar', $1) RETURNING id",
        domain,
    )
    matched_job_id = await tenant_a_conn.fetchval(
        """
        INSERT INTO jobs (id, company_id, external_id, title, location, country)
        VALUES (gen_random_uuid(), $1, $2, 'Staff Backend Engineer', 'Bengaluru', 'IN')
        RETURNING id
        """,
        company_id,
        f"radar-test-matched-{suffix}",
    )
    unmatched_job_id = await tenant_a_conn.fetchval(
        """
        INSERT INTO jobs (id, company_id, external_id, title, location, country)
        VALUES (gen_random_uuid(), $1, $2, 'Data Analyst', NULL, 'IN')
        RETURNING id
        """,
        company_id,
        f"radar-test-unmatched-{suffix}",
    )
    await tenant_a_conn.execute(
        """
        INSERT INTO matches (id, user_id, job_id, score, ev_score, tier)
        VALUES (gen_random_uuid(), $1, $2, 0.87, 69300.0, 1)
        """,
        tenant_a_id,
        matched_job_id,
    )

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.get(
            "/api/jobs?limit=500", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    by_id = {row["job_id"]: row for row in response.json()}

    matched = by_id[f"radar-test-matched-{suffix}"]
    assert matched["title"] == "Staff Backend Engineer"
    assert matched["company"] == "Acme Radar"
    assert matched["location"] == "Bengaluru"
    assert matched["tier"] == 1
    assert matched["ev_score"] == 69300.0
    assert matched["match_score"] == 0.87

    unmatched = by_id[f"radar-test-unmatched-{suffix}"]
    assert unmatched["title"] == "Data Analyst"
    # No matches row for this job -> the LEFT JOIN leaves these genuinely
    # absent rather than a fabricated placeholder.
    assert unmatched["tier"] is None
    assert unmatched["ev_score"] is None
    assert unmatched["match_score"] is None
    # location was NULL on the row -> falls back to country per the endpoint.
    assert unmatched["location"] == "IN"


async def test_list_jobs_without_a_token_is_rejected(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/jobs")
    assert response.status_code == 401


async def test_radar_signals_default_feed_url_detects_nothing(db_pool):
    """Default feed_url is an http(s) URL; scan_funding_rss's own contract is
    to return no signals for a bare URL (fetching it is left to the poller),
    so the honest response here is zero — not a fabricated hit."""
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/radar/signals")

    assert response.status_code == 200
    body = response.json()
    assert body["signals_detected"] == 0
    assert body["active_radar_sources"] == ["Funding RSS", "Apollo Spikes", "Exec Departures"]


async def test_radar_signals_parses_real_funding_xml(db_pool):
    """feed_url doubles as a raw-XML input path (see scan_funding_rss) — the
    endpoint has no live network dependency here, so this exercises the real
    parser rather than mocking it away."""
    expected = await scan_funding_rss(FUNDING_XML)
    assert len(expected) == 1, "sanity check: fixture should yield exactly one funding signal"

    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/radar/signals", params={"feed_url": FUNDING_XML})

    assert response.status_code == 200
    assert response.json()["signals_detected"] == len(expected)
