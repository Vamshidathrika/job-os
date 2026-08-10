import uuid
import pytest
import asyncpg

pytestmark = [pytest.mark.security, pytest.mark.asyncio(loop_scope="session")]

# RLS column per jobos/db/rls.py: applications/people are scoped by user_id,
# credentials is scoped by tenant_id. In this schema tenant_id == user_id
# (tenants.user_id is 1:1), so the fixed TENANT_A_ID/TENANT_B_ID from
# conftest.py double as the user_id values below.

async def test_tenant_a_cannot_read_tenant_b_applications(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    await tenant_a_conn.execute("INSERT INTO applications (id, user_id, path) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Test App")

    rows = await tenant_b_conn.fetch("SELECT * FROM applications WHERE id = $1", app_id)
    assert len(rows) == 0

async def test_tenant_a_cannot_read_tenant_b_people(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID) -> None:
    person_id = uuid.uuid4()
    await tenant_a_conn.execute("INSERT INTO people (id, user_id, full_name) VALUES ($1, $2, $3)", person_id, tenant_a_id, "Test Person")

    rows = await tenant_b_conn.fetch("SELECT * FROM people WHERE id = $1", person_id)
    assert len(rows) == 0

async def test_tenant_a_cannot_read_tenant_b_credentials(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID) -> None:
    cred_id = uuid.uuid4()
    # provider is unique per (tenant_id, provider) — randomize so reruns against
    # a persistent (non-ephemeral) test DB don't collide with prior runs.
    await tenant_a_conn.execute("INSERT INTO credentials (id, tenant_id, provider) VALUES ($1, $2, $3)", cred_id, tenant_a_id, f"test-{cred_id.hex[:8]}")

    rows = await tenant_b_conn.fetch("SELECT * FROM credentials WHERE id = $1", cred_id)
    assert len(rows) == 0

async def test_tenant_a_cannot_update_tenant_b_data(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    await tenant_a_conn.execute("INSERT INTO applications (id, user_id, path) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Original Path")

    result = await tenant_b_conn.execute("UPDATE applications SET path = $1 WHERE id = $2", "Hacked Path", app_id)
    assert result == "UPDATE 0"

    row = await tenant_a_conn.fetchrow("SELECT path FROM applications WHERE id = $1", app_id)
    assert row is not None
    assert row["path"] == "Original Path"

async def test_tenant_a_cannot_delete_tenant_b_data(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    await tenant_a_conn.execute("INSERT INTO applications (id, user_id, path) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Delete Me")

    result = await tenant_b_conn.execute("DELETE FROM applications WHERE id = $1", app_id)
    assert result == "DELETE 0"

    row = await tenant_a_conn.fetchrow("SELECT id FROM applications WHERE id = $1", app_id)
    assert row is not None

@pytest.mark.parametrize("table", ["applications", "people", "credentials"])
async def test_cross_tenant_read_on_all_rls_tables(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID, table: str) -> None:
    row_id = uuid.uuid4()
    if table == "credentials":
        await tenant_a_conn.execute(f"INSERT INTO {table} (id, tenant_id, provider) VALUES ($1, $2, $3)", row_id, tenant_a_id, f"test-{row_id.hex[:8]}")
    else:
        await tenant_a_conn.execute(f"INSERT INTO {table} (id, user_id) VALUES ($1, $2)", row_id, tenant_a_id)

    rows = await tenant_b_conn.fetch(f"SELECT * FROM {table} WHERE id = $1", row_id)
    assert len(rows) == 0
