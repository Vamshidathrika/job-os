"""Integration tests for the calibration feedback loop and ghost detection."""

import uuid

import pytest

from jobos.calibration.ghost_tracker import detect_ghost_jobs_from_db
from jobos.calibration.loop import MIN_OUTCOMES_FOR_RECALIBRATION, CalibrationLoop

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean_tables(tenant_a_conn):
    for table in ("agent_decisions", "applications"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")
    yield
    for table in ("agent_decisions", "applications"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")


async def _make_job(conn) -> uuid.UUID:
    company_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO companies (id, name, domain) VALUES ($1, $2, $3)",
        company_id, "Acme", f"acme-{company_id.hex[:8]}.example",
    )
    job_id = uuid.uuid4()
    await conn.execute(
        "INSERT INTO jobs (id, company_id, external_id, title, first_seen_at) "
        "VALUES ($1, $2, $3, $4, now() - interval '90 days')",
        job_id, company_id, f"ext-{job_id.hex[:6]}", "Backend Engineer",
    )
    return job_id


async def test_recorded_outcome_is_persisted(tenant_a_conn, tenant_a_id):
    """The old implementation logged and dropped the outcome on the floor."""
    loop = CalibrationLoop(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    job_id = await _make_job(tenant_a_conn)

    await loop.record_outcome(str(job_id), "interview", {"source": "referral"})

    row = await tenant_a_conn.fetchrow(
        "SELECT outputs FROM agent_decisions WHERE module = 'calibration'"
    )
    assert row is not None
    assert "interview" in row["outputs"]


async def test_recording_interview_updates_the_application(tenant_a_conn, tenant_a_id):
    loop = CalibrationLoop(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    job_id = await _make_job(tenant_a_conn)
    await tenant_a_conn.execute(
        "INSERT INTO applications (id, user_id, job_id, submitted_at, status) "
        "VALUES ($1, $2, $3, now(), 'pending')",
        uuid.uuid4(), tenant_a_id, job_id,
    )

    await loop.record_outcome(str(job_id), "interview", {})

    row = await tenant_a_conn.fetchrow(
        "SELECT status, interview_scheduled_at FROM applications WHERE job_id = $1", job_id
    )
    assert row["status"] == "interview"
    assert row["interview_scheduled_at"] is not None


async def test_recalibration_holds_weights_without_enough_data(tenant_a_conn, tenant_a_id):
    loop = CalibrationLoop(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    job_id = await _make_job(tenant_a_conn)
    await loop.record_outcome(str(job_id), "reject", {})

    result = await loop.recalibrate()

    assert result["match_threshold_adj"] == 0.0
    assert result["ev_weight_adj"] == 0.0
    assert result["reason"] == "insufficient_data"


async def test_poor_results_tighten_the_match_threshold(tenant_a_conn, tenant_a_id):
    """Lots of rejections should make the matcher choosier, not stay static."""
    loop = CalibrationLoop(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    job_id = await _make_job(tenant_a_conn)
    for _ in range(MIN_OUTCOMES_FOR_RECALIBRATION):
        await loop.record_outcome(str(job_id), "reject", {})

    result = await loop.recalibrate()

    assert result["sample_size"] == MIN_OUTCOMES_FOR_RECALIBRATION
    assert result["interview_rate"] == 0.0
    assert result["match_threshold_adj"] > 0, "should tighten after zero interviews"
    assert result["ev_weight_adj"] < 0


async def test_strong_results_loosen_the_match_threshold(tenant_a_conn, tenant_a_id):
    loop = CalibrationLoop(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    job_id = await _make_job(tenant_a_conn)
    for _ in range(MIN_OUTCOMES_FOR_RECALIBRATION):
        await loop.record_outcome(str(job_id), "interview", {})

    result = await loop.recalibrate()

    assert result["interview_rate"] == 1.0
    assert result["match_threshold_adj"] < 0, "should widen the funnel when results are strong"


async def test_adjustments_are_bounded(tenant_a_conn, tenant_a_id):
    loop = CalibrationLoop(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    job_id = await _make_job(tenant_a_conn)
    for _ in range(60):
        await loop.record_outcome(str(job_id), "reject", {})

    result = await loop.recalibrate()

    assert abs(result["match_threshold_adj"]) <= 0.10
    assert abs(result["ev_weight_adj"]) <= 0.10


async def test_ghost_detection_uses_real_application_history(tenant_a_conn, tenant_a_id):
    job_id = await _make_job(tenant_a_conn)
    # Three applications, zero responses, on a 90-day-old listing.
    for _ in range(3):
        await tenant_a_conn.execute(
            "INSERT INTO applications (id, user_id, job_id, submitted_at, status) "
            "VALUES ($1, $2, $3, now(), 'pending')",
            uuid.uuid4(), tenant_a_id, job_id,
        )

    flagged = await detect_ghost_jobs_from_db(tenant_a_conn)

    match = next((j for j in flagged if j["id"] == str(job_id)), None)
    assert match is not None
    assert match["ghost_score"] >= 0.5
    assert "zero responses" in match["reason"]
    assert "90 days ago" in match["reason"]
