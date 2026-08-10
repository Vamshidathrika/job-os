"""Integration tests for importing a profile into the Career Graph."""

import csv
import io
import zipfile

import pytest

from jobos.onboarding.linkedin_import import import_profile

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _csv(rows):
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


@pytest.fixture
def export_zip(tmp_path):
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Positions.csv",
            _csv([
                ["Company Name", "Title", "Description", "Location", "Started On", "Finished On"],
                ["Acme", "Backend Engineer", "Built a Redis cache cutting p99 45%", "Bengaluru", "Jan 2022", "Mar 2024"],
            ]),
        )
        archive.writestr("Skills.csv", _csv([["Name"], ["Python"]]))
        archive.writestr(
            "Connections.csv",
            _csv([
                ["First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"],
                ["Ravi", "Kumar", "https://linkedin.com/in/ravi", "", "Globex", "Engineering Manager", "01 Feb 2024"],
            ]),
        )
    return str(path)


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people")
    yield
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people")


async def test_positions_become_unverified_bullets(tenant_a_conn, tenant_a_id, export_zip):
    counts = await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)

    assert counts["bullets"] >= 1
    row = await tenant_a_conn.fetchrow(
        "SELECT company, role, bullet_text, verification_status FROM cg_bullets LIMIT 1"
    )
    assert row["company"] == "Acme"
    assert row["verification_status"] == "unverified", (
        "imported history is claimed, not verified; the tailorer may only use verified bullets"
    )


async def test_connections_become_people(tenant_a_conn, tenant_a_id, export_zip):
    counts = await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)

    assert counts["connections"] == 1
    row = await tenant_a_conn.fetchrow("SELECT full_name, company_domain, source FROM people")
    assert row["full_name"] == "Ravi Kumar"
    assert row["source"] == "linkedin_connection"


async def test_import_is_idempotent(tenant_a_conn, tenant_a_id, export_zip):
    await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)
    await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)

    assert await tenant_a_conn.fetchval("SELECT count(*) FROM people") == 1
    bullets = await tenant_a_conn.fetchval("SELECT count(*) FROM cg_bullets")
    assert bullets >= 1
    assert bullets < 4, "re-import must not duplicate bullets"


async def test_import_is_tenant_isolated(tenant_a_conn, tenant_b_conn, tenant_a_id, export_zip):
    await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)

    assert await tenant_b_conn.fetchval("SELECT count(*) FROM people") == 0
