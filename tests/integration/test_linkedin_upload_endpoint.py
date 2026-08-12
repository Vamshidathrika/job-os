"""Integration test for POST /api/onboarding/linkedin-import.

No static fixture zip exists in this repo (checked `find tests -iname
"*linkedin*"` — only tests/unit/test_linkedin_import.py, which builds its
export.zip on the fly with a tmp_path fixture). The most directly relevant
existing test is tests/integration/test_profile_import.py, which exercises
import_profile() itself — the exact function this endpoint wraps. Reusing
that same zip-building approach here instead of a FIXTURE_ZIP path.
"""

import csv
import io
import zipfile

import httpx
import pytest

from jobos.api import main as api_main
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _csv(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


@pytest.fixture
def export_zip(tmp_path):
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Positions.csv",
            _csv(
                [
                    ["Company Name", "Title", "Description", "Location", "Started On", "Finished On"],
                    ["Acme", "Backend Engineer", "Built a Redis cache cutting p99 45%", "Bengaluru", "Jan 2022", "Mar 2024"],
                ]
            ),
        )
        archive.writestr("Skills.csv", _csv([["Name"], ["Python"]]))
        archive.writestr(
            "Connections.csv",
            _csv(
                [
                    ["First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"],
                    ["Ravi", "Kumar", "https://linkedin.com/in/ravi", "", "Globex", "Engineering Manager", "01 Feb 2024"],
                ]
            ),
        )
    return str(path)


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people WHERE source = 'linkedin_connection'")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    api_main.app.state.pool = db_pool
    yield
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people WHERE source = 'linkedin_connection'")
    await tenant_a_conn.execute("DELETE FROM api_tokens")


async def test_uploaded_zip_is_imported_and_summary_returned(
    tenant_a_conn, tenant_a_id, db_pool, export_zip
):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")

    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with open(export_zip, "rb") as f:
            response = await client.post(
                "/api/onboarding/linkedin-import",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("linkedin_export.zip", f, "application/zip")},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["bullets"] > 0

    stored = await tenant_a_conn.fetchval("SELECT count(*) FROM cg_bullets")
    assert stored == body["bullets"]


async def test_upload_without_a_file_is_rejected(tenant_a_conn, tenant_a_id, db_pool):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")

    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/onboarding/linkedin-import",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422
