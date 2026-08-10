"""Integration tests for the hiring radar's writes to the tenant universe."""

import datetime

import pytest

from jobos.hiring_radar.signals import HiringSignal, SignalType, process_signals

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

DOMAIN = "radar-target.example"


def _signal(action: str = "add_to_universe") -> HiringSignal:
    return HiringSignal(
        company_name="Radar Target",
        company_domain=DOMAIN,
        signal_type=SignalType.FUNDING,
        prediction="likely to hire backend engineers",
        action=action,
        confidence=0.9,
        detected_at=datetime.datetime.now(datetime.timezone.utc),
    )


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM tenant_company_universe")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE domain = $1", DOMAIN)
    yield
    await tenant_a_conn.execute("DELETE FROM tenant_company_universe")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE domain = $1", DOMAIN)


async def test_signals_reach_the_tenant_universe(db_pool, tenant_a_conn, tenant_a_id):
    """The previous version silently inserted zero rows under RLS."""
    written = await process_signals([_signal()], db_pool, tenant_ids=[str(tenant_a_id)])

    assert written == 1

    row = await tenant_a_conn.fetchrow(
        "SELECT company_domain, signal_type, action FROM tenant_company_universe "
        "WHERE company_domain = $1",
        DOMAIN,
    )
    assert row is not None, "signal must actually land in the tenant's universe"
    assert row["signal_type"] == "FUNDING"
    assert row["action"] == "add_to_universe"


async def test_company_is_upserted_globally(db_pool, tenant_a_id):
    await process_signals([_signal()], db_pool, tenant_ids=[str(tenant_a_id)])

    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM companies WHERE domain = $1", DOMAIN)
    assert count == 1


async def test_reprocessing_updates_in_place(db_pool, tenant_a_conn, tenant_a_id):
    await process_signals([_signal(action="watch")], db_pool, tenant_ids=[str(tenant_a_id)])
    await process_signals([_signal(action="add_to_universe")], db_pool, tenant_ids=[str(tenant_a_id)])

    rows = await tenant_a_conn.fetch(
        "SELECT action FROM tenant_company_universe WHERE company_domain = $1", DOMAIN
    )
    assert len(rows) == 1, "must upsert, not duplicate"
    assert rows[0]["action"] == "add_to_universe"


async def test_signals_are_written_per_tenant(db_pool, tenant_a_conn, tenant_b_conn, tenant_a_id, tenant_b_id):
    written = await process_signals(
        [_signal()], db_pool, tenant_ids=[str(tenant_a_id), str(tenant_b_id)]
    )

    assert written == 2
    assert await tenant_a_conn.fetchval(
        "SELECT count(*) FROM tenant_company_universe WHERE company_domain = $1", DOMAIN
    ) == 1
    assert await tenant_b_conn.fetchval(
        "SELECT count(*) FROM tenant_company_universe WHERE company_domain = $1", DOMAIN
    ) == 1


async def test_no_tenants_writes_nothing_and_says_so(db_pool):
    """An empty target list must be reported, not silently swallowed."""
    assert await process_signals([_signal()], db_pool, tenant_ids=[]) == 0


async def test_no_signals_is_a_noop(db_pool, tenant_a_id):
    assert await process_signals([], db_pool, tenant_ids=[str(tenant_a_id)]) == 0
