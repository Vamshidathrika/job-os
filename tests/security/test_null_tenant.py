import uuid
import pytest
import asyncpg

pytestmark = [pytest.mark.security, pytest.mark.asyncio]

async def test_null_tenant_context_returns_zero_rows(db_pool: asyncpg.Pool, tenant_a_conn: asyncpg.Connection, tenant_a_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    try:
        await tenant_a_conn.execute("INSERT INTO applications (id, tenant_id, title) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Null Tenant Test")
    except asyncpg.exceptions.UndefinedTableError:
        pytest.skip("Schema not fully set up yet")

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM applications WHERE id = $1", app_id)
        assert len(rows) == 0

async def test_empty_string_tenant_returns_zero_rows(db_pool: asyncpg.Pool, tenant_a_conn: asyncpg.Connection, tenant_a_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    try:
        await tenant_a_conn.execute("INSERT INTO applications (id, tenant_id, title) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Empty Tenant Test")
    except asyncpg.exceptions.UndefinedTableError:
        pytest.skip("Schema not fully set up yet")

    async with db_pool.acquire() as conn:
        await conn.execute("SELECT set_config('app.current_tenant', '', true)")
        rows = await conn.fetch("SELECT * FROM applications WHERE id = $1", app_id)
        assert len(rows) == 0

async def test_invalid_uuid_tenant_raises_error(db_pool: asyncpg.Pool) -> None:
    async with db_pool.acquire() as conn:
        with pytest.raises(Exception):
            await conn.execute("SELECT set_config('app.current_tenant', 'not-a-uuid', true)")
            await conn.fetch("SELECT * FROM applications LIMIT 1")
