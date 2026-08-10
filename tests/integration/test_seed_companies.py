"""Integration tests for seeding the company universe."""

import pytest

from jobos.ingestion.seed_companies import seed_companies

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

YAML = """
companies:
  - name: Acme
    domain: acme.example
    ats_type: greenhouse
    ats_identifier: acme
  - name: Globex
    domain: globex.example
    ats_type: lever
    ats_identifier: globex
"""


@pytest.fixture
def seed_file(tmp_path):
    path = tmp_path / "seed.yaml"
    path.write_text(YAML)
    return str(path)


@pytest.fixture(autouse=True)
async def clean(db_pool, setup_schema):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")
    yield
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")


async def test_seeding_inserts_companies(db_pool, seed_file):
    async with db_pool.acquire() as conn:
        counts = await seed_companies(conn, seed_file)

        assert counts["inserted"] == 2
        row = await conn.fetchrow("SELECT * FROM companies WHERE domain = 'acme.example'")
        assert row["ats_type"] == "greenhouse"
        assert row["ats_identifier"] == "acme"


async def test_seeding_is_idempotent(db_pool, seed_file):
    async with db_pool.acquire() as conn:
        await seed_companies(conn, seed_file)
        counts = await seed_companies(conn, seed_file)

        assert counts["inserted"] == 0
        assert counts["updated"] == 2
        total = await conn.fetchval(
            "SELECT count(*) FROM companies WHERE domain LIKE '%.example'"
        )
        assert total == 2


async def test_entry_missing_required_fields_is_rejected(db_pool, tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("companies:\n  - name: NoDomain\n")

    async with db_pool.acquire() as conn:
        with pytest.raises(ValueError, match="domain"):
            await seed_companies(conn, str(path))


async def test_seeded_companies_are_pollable(db_pool, seed_file):
    """The ingestion worker only polls rows with both ATS fields set."""
    async with db_pool.acquire() as conn:
        await seed_companies(conn, seed_file)
        pollable = await conn.fetchval(
            "SELECT count(*) FROM companies "
            "WHERE domain LIKE '%.example' AND ats_type IS NOT NULL AND ats_identifier IS NOT NULL"
        )
    assert pollable == 2
