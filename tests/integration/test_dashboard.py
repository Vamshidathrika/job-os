"""Integration tests for dashboard stats and timeline against real data."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from jobos.dashboard.stats import get_pipeline_stats
from jobos.dashboard.timeline import get_activity_timeline

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean_tables(tenant_a_conn):
    for table in ("action_queue", "applications", "matches"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")
    yield
    for table in ("action_queue", "applications", "matches"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")


async def _make_job(conn) -> uuid.UUID:
    """Create a company + job pair to hang applications off."""
    company_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO companies (id, name, domain) VALUES ($1, $2, $3)",
        company_id,
        "Acme Corp",
        f"acme-{company_id.hex[:8]}.example",
    )
    job_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO jobs (id, company_id, external_id, title) VALUES ($1, $2, $3, $4)",
        job_id,
        company_id,
        f"ext-{job_id.hex[:6]}",
        "Backend Engineer",
    )
    return job_id


async def test_stats_are_zero_for_an_empty_tenant(tenant_a_conn, tenant_a_id):
    """An empty pipeline must report zeros, not the old mock figures."""
    stats = await get_pipeline_stats(tenant_a_conn, tenant_id=str(tenant_a_id))

    assert stats["jobs_tracked"] == 0
    assert stats["applications_sent"] == 0
    assert stats["response_rate"] == 0.0
    assert stats["avg_days_to_interview"] is None
    # The mock always claimed these regardless of reality.
    assert stats != {
        "jobs_tracked": 120,
        "applications_sent": 45,
        "interviews_scheduled": 5,
        "offers_received": 1,
        "response_rate": 0.11,
        "avg_days_to_interview": 14.5,
    }


async def test_stats_count_real_rows(tenant_a_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    submitted = datetime.now(timezone.utc) - timedelta(days=10)

    await tenant_a_conn.execute(
        "INSERT INTO matches (id, user_id, job_id, score) VALUES ($1, $2, $3, $4)",
        uuid.uuid4(), tenant_a_id, job_id, 0.9,
    )
    # One interviewed (submitted 10d ago, interview 4d later) and one pending.
    await tenant_a_conn.execute(
        "INSERT INTO applications (id, user_id, job_id, submitted_at, interview_scheduled_at, status) "
        "VALUES ($1, $2, $3, $4, $5, 'interview')",
        uuid.uuid4(), tenant_a_id, job_id, submitted, submitted + timedelta(days=4),
    )
    await tenant_a_conn.execute(
        "INSERT INTO applications (id, user_id, job_id, submitted_at, status) "
        "VALUES ($1, $2, $3, $4, 'pending')",
        uuid.uuid4(), tenant_a_id, job_id, submitted,
    )

    stats = await get_pipeline_stats(tenant_a_conn, tenant_id=str(tenant_a_id))

    assert stats["jobs_tracked"] == 1
    assert stats["applications_sent"] == 2
    assert stats["interviews_scheduled"] == 1
    assert stats["response_rate"] == 0.5
    assert stats["avg_days_to_interview"] == 4.0


async def test_stats_are_tenant_isolated(tenant_a_conn, tenant_b_conn, tenant_a_id, tenant_b_id):
    job_id = await _make_job(tenant_a_conn)
    await tenant_a_conn.execute(
        "INSERT INTO applications (id, user_id, job_id, submitted_at, status) "
        "VALUES ($1, $2, $3, now(), 'pending')",
        uuid.uuid4(), tenant_a_id, job_id,
    )

    b_stats = await get_pipeline_stats(tenant_b_conn, tenant_id=str(tenant_b_id))

    assert b_stats["applications_sent"] == 0, "tenant B must not see tenant A's pipeline"


async def test_timeline_reflects_real_events(tenant_a_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    await tenant_a_conn.execute(
        "INSERT INTO applications (id, user_id, job_id, submitted_at, status) "
        "VALUES ($1, $2, $3, now() - interval '1 day', 'interview')",
        uuid.uuid4(), tenant_a_id, job_id,
    )

    timeline = await get_activity_timeline(tenant_a_conn, tenant_id=str(tenant_a_id))

    assert len(timeline) == 1
    assert timeline[0]["type"] == "interview_scheduled"
    assert timeline[0]["details"]["company"] == "Acme Corp"
    assert timeline[0]["details"]["role"] == "Backend Engineer"
    # The mock always returned these two fabricated entries.
    assert timeline[0]["id"] not in ("act-1", "act-2")


async def test_timeline_includes_completed_queue_actions(tenant_a_conn, tenant_a_id):
    await tenant_a_conn.execute(
        "INSERT INTO action_queue (user_id, action_type, payload, band, status) "
        "VALUES ($1, 'send_email', $2::jsonb, 'A', 'completed')",
        tenant_a_id,
        '{"company": "Globex", "role": "SRE"}',
    )

    timeline = await get_activity_timeline(tenant_a_conn, tenant_id=str(tenant_a_id))

    assert [e["type"] for e in timeline] == ["send_email"]
    assert timeline[0]["details"]["company"] == "Globex"


async def test_timeline_excludes_events_outside_window(tenant_a_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    await tenant_a_conn.execute(
        "INSERT INTO applications (id, user_id, job_id, submitted_at, status) "
        "VALUES ($1, $2, $3, now() - interval '90 days', 'pending')",
        uuid.uuid4(), tenant_a_id, job_id,
    )

    timeline = await get_activity_timeline(tenant_a_conn, tenant_id=str(tenant_a_id), days=30)

    assert timeline == []
