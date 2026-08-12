"""Integration tests for stage_upload_resume against the real test DB."""

import uuid

import pytest

from jobos.config import Settings
from jobos.db.models import EMBEDDING_DIM
from jobos.runner.pipeline import (
    NoJobFoundError,
    NoVerifiedBulletsError,
    stage_upload_resume,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")
    yield
    await tenant_a_conn.execute("DELETE FROM cg_bullets")


async def _seed_job(db_pool, title: str = "Backend Engineer") -> uuid.UUID:
    async with db_pool.acquire() as conn:
        company_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO companies (id, name, domain) VALUES ($1, $2, $3)",
            company_id, "Acme", f"acme-{company_id.hex[:8]}.example",
        )
        job_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO jobs (id, company_id, external_id, title, description, country, embedding) "
            "VALUES ($1, $2, $3, $4, $5, 'IN', $6::vector)",
            job_id, company_id, f"ext-{job_id.hex[:6]}", title,
            "Build backend services with Python and Postgres.",
            str([0.01] * EMBEDDING_DIM),
        )
        return job_id


async def test_uploads_tailored_resume_and_returns_real_drive_ids(
    tenant_a_conn, tenant_a_id, db_pool, mocker
):
    job_id = await _seed_job(db_pool)
    bullet_id = await tenant_a_conn.fetchval(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Prior Co', 'Backend Engineer', "
        "'Built Python services on Postgres', 'verified') RETURNING id",
        tenant_a_id,
    )
    mocker.patch(
        "jobos.tailorer.generator.acompletion",
        return_value={
            "choices": [{"message": {"content": (
                '{"used_bullet_ids": ["' + str(bullet_id) + '"], "tailored_text": "Tailored body"}'
            )}}]
        },
    )
    mock_drive = mocker.AsyncMock()
    mock_drive.ensure_folder.return_value = {"folder_id": "folder-1"}
    mock_drive.upload_resume.return_value = {"file_id": "real-file-1", "web_view_link": "https://drive/real-file-1"}
    mocker.patch("jobos.runner.pipeline.DriveClient", return_value=mock_drive)

    result = await stage_upload_resume(db_pool, str(tenant_a_id), str(job_id), Settings())

    assert result["file_id"] == "real-file-1"
    assert result["web_view_link"] == "https://drive/real-file-1"
    upload_kwargs = mock_drive.upload_resume.call_args.kwargs
    assert upload_kwargs["folder_id"] == "folder-1"
    assert "Tailored body" == upload_kwargs["text_content"]


async def test_missing_job_raises(tenant_a_conn, tenant_a_id, db_pool):
    with pytest.raises(NoJobFoundError):
        await stage_upload_resume(
            db_pool, str(tenant_a_id), str(uuid.uuid4()), Settings()
        )


async def test_no_verified_bullets_raises_rather_than_fabricating(
    tenant_a_conn, tenant_a_id, db_pool
):
    """An unverified-only Career Graph must refuse, not tailor from unverifiable claims."""
    job_id = await _seed_job(db_pool)
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Prior Co', 'Engineer', 'Unverified claim', 'unverified')",
        tenant_a_id,
    )

    with pytest.raises(NoVerifiedBulletsError):
        await stage_upload_resume(db_pool, str(tenant_a_id), str(job_id), Settings())
