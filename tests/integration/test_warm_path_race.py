"""Integration tests for the 7-day warm-path race.

The race is the product's core mechanism: it holds a high-value application
back while warm paths are attempted, and only releases it to cold apply once
the week is genuinely up. The previous implementation was a logging shell
whose resolve_race() always returned cold_apply_fallback / days_elapsed 7.
"""

import uuid
from datetime import timedelta

import pytest

from jobos.action_queue.queue import ActionQueue
from jobos.warm_path.race import (
    OUTCOME_COLD_APPLY_FALLBACK,
    OUTCOME_RUNNING,
    OUTCOME_WARM_RESPONSE,
    RaceNotStartedError,
    WarmPathRace,
    find_expired_races,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

SEQUENCE = [
    {"subject": "s1", "body": "b1", "send_delay_hours": 0},
    {"subject": "s2", "body": "b2", "send_delay_hours": 72},
    {"subject": "s3", "body": "b3", "send_delay_hours": 144},
]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM warm_path_races")
    await tenant_a_conn.execute("DELETE FROM action_queue")
    yield
    await tenant_a_conn.execute("DELETE FROM warm_path_races")
    await tenant_a_conn.execute("DELETE FROM action_queue")


async def _make_job(conn) -> uuid.UUID:
    company_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO companies (id, name, domain) VALUES ($1, $2, $3)",
        company_id, "Acme", f"acme-{company_id.hex[:8]}.example",
    )
    job_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO jobs (id, company_id, external_id, title) VALUES ($1, $2, $3, $4)",
        job_id, company_id, f"ext-{job_id.hex[:6]}", "Backend Engineer",
    )
    return job_id


def _race(conn, tenant_id, job_id) -> WarmPathRace:
    return WarmPathRace(conn=conn, job_id=str(job_id), tenant_id=str(tenant_id))


async def test_a_running_race_does_not_report_a_fallback(tenant_a_conn, tenant_a_id):
    """The old shell always said cold_apply_fallback, releasing the very
    application the race exists to hold."""
    job_id = await _make_job(tenant_a_conn)
    race = _race(tenant_a_conn, tenant_a_id, job_id)
    await race.start_race()

    result = await race.resolve_race()

    assert result["outcome"] == OUTCOME_RUNNING
    assert result["days_elapsed"] < 1
    assert result["outcome"] != OUTCOME_COLD_APPLY_FALLBACK


async def test_race_state_survives_a_new_instance(tenant_a_conn, tenant_a_id):
    """A week-long race outlives any process that started it."""
    job_id = await _make_job(tenant_a_conn)
    await _race(tenant_a_conn, tenant_a_id, job_id).start_race()

    reborn = _race(tenant_a_conn, tenant_a_id, job_id)
    assert await reborn.check_response() is False
    assert (await reborn.resolve_race())["outcome"] == OUTCOME_RUNNING


async def test_touches_are_scheduled_across_the_week(tenant_a_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    await _race(tenant_a_conn, tenant_a_id, job_id).start_race(touches=SEQUENCE)

    rows = await tenant_a_conn.fetch(
        "SELECT scheduled_for FROM action_queue WHERE action_type = 'referral_touch' "
        "ORDER BY scheduled_for"
    )
    assert len(rows) == 3

    spread = rows[-1]["scheduled_for"] - rows[0]["scheduled_for"]
    assert timedelta(days=5) < spread < timedelta(days=7)


async def test_only_the_due_touch_is_dequeued(tenant_a_conn, tenant_a_id):
    """Day-3 and day-6 follow-ups must not all fire on day 0."""
    job_id = await _make_job(tenant_a_conn)
    await _race(tenant_a_conn, tenant_a_id, job_id).start_race(touches=SEQUENCE)

    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    due = await queue.dequeue_batch(band="B", limit=10)

    assert len(due) == 1
    assert due[0]["payload"]["touch_number"] == 1


async def test_a_reply_wins_the_race_and_stops_the_sequence(tenant_a_conn, tenant_a_id):
    """Continuing to send follow-ups after someone replied is the rudest bug."""
    job_id = await _make_job(tenant_a_conn)
    race = _race(tenant_a_conn, tenant_a_id, job_id)
    await race.start_race(touches=SEQUENCE)

    await race.record_response("referral")

    result = await race.resolve_race()
    assert result["outcome"] == OUTCOME_WARM_RESPONSE
    assert result["channel"] == "referral"

    pending = await tenant_a_conn.fetchval(
        "SELECT count(*) FROM action_queue WHERE action_type = 'referral_touch' AND status = 'pending'"
    )
    assert pending == 0, "pending touches must be cancelled once a reply lands"


async def test_first_reply_wins(tenant_a_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    race = _race(tenant_a_conn, tenant_a_id, job_id)
    await race.start_race()

    await race.record_response("referral")
    await race.record_response("recruiter")

    assert (await race.resolve_race())["channel"] == "referral"


async def test_check_response_is_channel_aware(tenant_a_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    race = _race(tenant_a_conn, tenant_a_id, job_id)
    await race.start_race()
    await race.record_response("referral")

    assert await race.check_response() is True
    assert await race.check_response("referral") is True
    assert await race.check_response("recruiter") is False


async def test_expired_race_falls_back_to_cold_apply(tenant_a_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    race = _race(tenant_a_conn, tenant_a_id, job_id)
    await race.start_race()

    # Wind the clock back past the deadline.
    await tenant_a_conn.execute(
        "UPDATE warm_path_races SET started_at = now() - interval '8 days', "
        "deadline_at = now() - interval '1 day' WHERE job_id = $1",
        job_id,
    )

    result = await race.resolve_race()

    assert result["outcome"] == OUTCOME_COLD_APPLY_FALLBACK
    assert result["days_elapsed"] >= 7


async def test_find_expired_races_only_returns_unanswered_overdue_races(
    tenant_a_conn, tenant_a_id
):
    overdue_job = await _make_job(tenant_a_conn)
    answered_job = await _make_job(tenant_a_conn)
    fresh_job = await _make_job(tenant_a_conn)

    for job_id in (overdue_job, answered_job, fresh_job):
        await _race(tenant_a_conn, tenant_a_id, job_id).start_race()

    await tenant_a_conn.execute(
        "UPDATE warm_path_races SET deadline_at = now() - interval '1 day' "
        "WHERE job_id = ANY($1::uuid[])",
        [overdue_job, answered_job],
    )
    await _race(tenant_a_conn, tenant_a_id, answered_job).record_response("referral")

    expired = await find_expired_races(tenant_a_conn)

    assert [e["job_id"] for e in expired] == [str(overdue_job)]


async def test_resolving_an_unstarted_race_raises(tenant_a_conn, tenant_a_id):
    """Never invent a resolution for a race that was never started."""
    job_id = await _make_job(tenant_a_conn)
    race = _race(tenant_a_conn, tenant_a_id, job_id)

    with pytest.raises(RaceNotStartedError):
        await race.resolve_race()


async def test_races_are_tenant_isolated(tenant_a_conn, tenant_b_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    await _race(tenant_a_conn, tenant_a_id, job_id).start_race()

    assert await tenant_b_conn.fetchval("SELECT count(*) FROM warm_path_races") == 0
    assert await find_expired_races(tenant_b_conn) == []


async def test_restarting_a_race_resets_its_outcome(tenant_a_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    race = _race(tenant_a_conn, tenant_a_id, job_id)
    await race.start_race()
    await race.record_response("referral")

    await race.start_race()

    assert await race.check_response() is False
    assert (await race.resolve_race())["outcome"] == OUTCOME_RUNNING
