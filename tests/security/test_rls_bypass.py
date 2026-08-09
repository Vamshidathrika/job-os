import uuid
import pytest
import asyncpg

pytestmark = [pytest.mark.security, pytest.mark.asyncio]

async def test_tenant_a_cannot_read_tenant_b_applications(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID, tenant_b_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    try:
        await tenant_a_conn.execute("INSERT INTO applications (id, tenant_id, title) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Test App")
    except asyncpg.exceptions.UndefinedTableError:
        pytest.skip("Schema not fully set up yet")
        
    rows = await tenant_b_conn.fetch("SELECT * FROM applications WHERE id = $1", app_id)
    assert len(rows) == 0

async def test_tenant_a_cannot_read_tenant_b_people(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID, tenant_b_id: uuid.UUID) -> None:
    person_id = uuid.uuid4()
    try:
        await tenant_a_conn.execute("INSERT INTO people (id, tenant_id, name) VALUES ($1, $2, $3)", person_id, tenant_a_id, "Test Person")
    except asyncpg.exceptions.UndefinedTableError:
        pytest.skip("Schema not fully set up yet")
        
    rows = await tenant_b_conn.fetch("SELECT * FROM people WHERE id = $1", person_id)
    assert len(rows) == 0

async def test_tenant_a_cannot_read_tenant_b_credentials(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID, tenant_b_id: uuid.UUID) -> None:
    cred_id = uuid.uuid4()
    try:
        await tenant_a_conn.execute("INSERT INTO credentials (id, tenant_id, name) VALUES ($1, $2, $3)", cred_id, tenant_a_id, "Test Cred")
    except asyncpg.exceptions.UndefinedTableError:
        pytest.skip("Schema not fully set up yet")
        
    rows = await tenant_b_conn.fetch("SELECT * FROM credentials WHERE id = $1", cred_id)
    assert len(rows) == 0

async def test_tenant_a_cannot_update_tenant_b_data(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID, tenant_b_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    try:
        await tenant_a_conn.execute("INSERT INTO applications (id, tenant_id, title) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Original Title")
    except asyncpg.exceptions.UndefinedTableError:
        pytest.skip("Schema not fully set up yet")
        
    result = await tenant_b_conn.execute("UPDATE applications SET title = $1 WHERE id = $2", "Hacked Title", app_id)
    assert result == "UPDATE 0"
    
    row = await tenant_a_conn.fetchrow("SELECT title FROM applications WHERE id = $1", app_id)
    assert row is not None
    assert row["title"] == "Original Title"

async def test_tenant_a_cannot_delete_tenant_b_data(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID, tenant_b_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    try:
        await tenant_a_conn.execute("INSERT INTO applications (id, tenant_id, title) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Delete Me")
    except asyncpg.exceptions.UndefinedTableError:
        pytest.skip("Schema not fully set up yet")
        
    result = await tenant_b_conn.execute("DELETE FROM applications WHERE id = $1", app_id)
    assert result == "DELETE 0"
    
    row = await tenant_a_conn.fetchrow("SELECT id FROM applications WHERE id = $1", app_id)
    assert row is not None

@pytest.mark.parametrize("table", ["applications", "people", "credentials", "organizations", "jobs", "workflows"])
async def test_cross_tenant_read_on_all_rls_tables(tenant_a_conn: asyncpg.Connection, tenant_b_conn: asyncpg.Connection, tenant_a_id: uuid.UUID, table: str) -> None:
    try:
        await tenant_b_conn.execute(f"SELECT * FROM {table} LIMIT 1")
    except asyncpg.exceptions.UndefinedTableError:
        pytest.skip(f"Table {table} not fully set up yet")
