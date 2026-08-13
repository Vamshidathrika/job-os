"""Integration test for the global ingestion pipeline.

Runs the real GlobalIngestionWorker against the real Postgres test database.
Only the two outbound network calls are stubbed — the ATS HTTP fetch and the
embedding provider — because neither has credentials in CI. Normalization,
SQL, casts and conflict handling are all exercised for real.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from jobos.config import Settings
from jobos.db.models import EMBEDDING_DIM
from jobos.workers.global_ingestion import GlobalIngestionWorker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 999,
            "title": "backend engineer",
            "location": {"name": "Hyderabad, India"},
            "content": "<p>Build scalable systems.</p>",
            "departments": [{"name": "Engineering"}],
            "offices": [{"name": "Hyderabad"}],
        }
    ]
}


@pytest.fixture(autouse=True)
async def clean_jobs(db_pool, setup_schema):
    """Other suites seed companies and jobs; the ingestion counters below are
    per-cycle totals across ALL companies, so start from a clean slate."""
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies")
    yield
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies")


@pytest.fixture
def seeded_company(db_pool, setup_schema):
    """Insert one greenhouse-backed company into the global companies table."""

    async def _seed():
        company_id = uuid.uuid4()
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO companies (id, name, domain, ats_type, ats_identifier) "
                "VALUES ($1, $2, $3, $4, $5)",
                company_id,
                "Acme Corp",
                f"acme-{company_id.hex[:8]}.example",
                "greenhouse",
                "acme",
            )
        return company_id

    return _seed


async def test_full_ingestion_cycle_writes_normalized_job(db_pool, seeded_company, mocker):
    company_id = await seeded_company()

    # Stub only the outbound calls: the ATS HTTP GET and the embedding provider.
    mocker.patch(
        "jobos.ingestion.poller.ATSPoller._fetch_with_retry",
        return_value=GREENHOUSE_PAYLOAD,
    )
    mocker.patch(
        "jobos.workers.global_ingestion.generate_embedding",
        return_value=[0.01] * EMBEDDING_DIM,
    )

    worker = GlobalIngestionWorker(pool=db_pool, settings=Settings())
    result = await worker.run_cycle()

    assert result["failed"] == 0, "no job should fail to insert"
    assert result["ingested"] == 1

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM jobs WHERE company_id = $1 AND external_id = $2",
            company_id,
            "999",
        )

    assert row is not None, "job row was not persisted"
    assert row["title"] == "Backend Engineer"  # normalizer title-cases
    assert row["country"] == "IN"  # Hyderabad -> India bucket
    assert row["ats_type"] == "greenhouse"
    assert "<p>" not in row["description"], "HTML should be stripped"
    assert row["id"] is not None, "id default must populate"


async def test_ingestion_cycle_is_idempotent_on_rerun(db_pool, seeded_company, mocker):
    """Re-polling the same posting updates in place rather than duplicating."""
    company_id = await seeded_company()

    mocker.patch(
        "jobos.ingestion.poller.ATSPoller._fetch_with_retry",
        return_value=GREENHOUSE_PAYLOAD,
    )
    mocker.patch(
        "jobos.workers.global_ingestion.generate_embedding",
        return_value=[0.01] * EMBEDDING_DIM,
    )

    worker = GlobalIngestionWorker(pool=db_pool, settings=Settings())
    await worker.run_cycle()
    await worker.run_cycle()

    async with db_pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count(*) FROM jobs WHERE company_id = $1 AND external_id = $2",
            company_id,
            "999",
        )

    assert count == 1


async def test_embedding_width_mismatch_is_counted_as_failure(db_pool, seeded_company, mocker):
    """A wrong-width embedding must be caught, not written as a corrupt vector."""
    await seeded_company()

    mocker.patch(
        "jobos.ingestion.poller.ATSPoller._fetch_with_retry",
        return_value=GREENHOUSE_PAYLOAD,
    )
    mocker.patch(
        "jobos.workers.global_ingestion.generate_embedding",
        return_value=[0.01] * (EMBEDDING_DIM + 1),
    )

    worker = GlobalIngestionWorker(pool=db_pool, settings=Settings())
    result = await worker.run_cycle()

    assert result["ingested"] == 0
    assert result["failed"] >= 1


async def test_ingestion_cycle_persists_extracted_hard_requirements(db_pool, seeded_company, mocker):
    """The extraction call added in global_ingestion.py (Task 1) must actually
    populate job_requirements on the success path.

    The other tests in this file only exercise extract_hard_requirements's
    catch-and-swallow failure branch implicitly (Settings() carries no real
    Groq key, so every acompletion call there fails and is logged, not
    raised). This test mocks the LLM boundary itself
    (jobos.ingestion.requirement_extractor.acompletion — the same seam the
    unit tests in test_requirement_extractor.py use) so the extraction
    actually succeeds, and asserts the resulting row lands in
    job_requirements with the expected hard_reqs.
    """
    company_id = await seeded_company()

    mocker.patch(
        "jobos.ingestion.poller.ATSPoller._fetch_with_retry",
        return_value=GREENHOUSE_PAYLOAD,
    )
    mocker.patch(
        "jobos.workers.global_ingestion.generate_embedding",
        return_value=[0.01] * EMBEDDING_DIM,
    )
    mock_response = mocker.MagicMock()
    mock_response.choices = [
        mocker.MagicMock(
            message=mocker.MagicMock(content='{"hard_requirements": ["Python", "Kubernetes"]}')
        )
    ]
    mocker.patch(
        "jobos.ingestion.requirement_extractor.acompletion",
        AsyncMock(return_value=mock_response),
    )

    worker = GlobalIngestionWorker(pool=db_pool, settings=Settings())
    result = await worker.run_cycle()

    assert result["ingested"] == 1

    async with db_pool.acquire() as conn:
        job_id = await conn.fetchval(
            "SELECT id FROM jobs WHERE company_id = $1 AND external_id = $2",
            company_id,
            "999",
        )
        row = await conn.fetchrow(
            "SELECT hard_reqs FROM job_requirements WHERE job_id = $1", job_id
        )

    assert row is not None, "job_requirements row was not persisted"
    assert "Python" in row["hard_reqs"]
    assert "Kubernetes" in row["hard_reqs"]
