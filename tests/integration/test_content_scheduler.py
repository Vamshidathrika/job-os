"""Integration tests for content scheduling against the real queue."""

from datetime import datetime, timedelta, timezone

import pytest

from jobos.content.scheduler import ContentScheduler

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean_queue(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM action_queue")
    yield
    await tenant_a_conn.execute("DELETE FROM action_queue")


async def test_scheduled_post_is_persisted_with_a_real_id(tenant_a_conn, tenant_a_id):
    """The old implementation always returned the literal 'mock_id_123'."""
    scheduler = ContentScheduler(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    publish_at = datetime.now(timezone.utc) + timedelta(days=1)

    result = await scheduler.schedule_post(
        {"content": "A real post", "hashtags": ["#backend"]},
        platform="linkedin",
        publish_at=publish_at,
    )

    assert result["post_id"] != "mock_id_123"

    row = await tenant_a_conn.fetchrow(
        "SELECT action_type, band, status, payload FROM action_queue WHERE id = $1::uuid",
        result["post_id"],
    )
    assert row["action_type"] == "publish_post"
    assert row["status"] == "pending"
    assert "A real post" in row["payload"]


async def test_scheduled_posts_are_tenant_isolated(tenant_a_conn, tenant_b_conn, tenant_a_id):
    scheduler = ContentScheduler(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await scheduler.schedule_post(
        {"content": "Tenant A only"},
        platform="linkedin",
        publish_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    visible_to_b = await tenant_b_conn.fetchval("SELECT count(*) FROM action_queue")
    assert visible_to_b == 0


async def test_optimal_time_is_in_the_future_on_a_weekday(tenant_a_conn, tenant_a_id):
    scheduler = ContentScheduler(conn=tenant_a_conn, tenant_id=str(tenant_a_id))

    optimal = scheduler.get_optimal_time(platform="linkedin", timezone_name="Asia/Kolkata")

    assert optimal > datetime.now(timezone.utc)
    assert optimal.weekday() < 5, "must not schedule onto a weekend"


async def test_optimal_time_falls_back_on_unknown_timezone(tenant_a_conn, tenant_a_id):
    scheduler = ContentScheduler(conn=tenant_a_conn, tenant_id=str(tenant_a_id))

    optimal = scheduler.get_optimal_time(platform="linkedin", timezone_name="Mars/Olympus")

    assert optimal > datetime.now(timezone.utc)
