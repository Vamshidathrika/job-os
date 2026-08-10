import uuid
import pytest
import asyncpg

pytestmark = [pytest.mark.security, pytest.mark.asyncio(loop_scope="session")]

async def test_null_tenant_context_returns_zero_rows(db_pool: asyncpg.Pool, tenant_a_conn: asyncpg.Connection, tenant_a_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    await tenant_a_conn.execute("INSERT INTO applications (id, user_id, path) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Null Tenant Test")

    async with db_pool.acquire() as conn:
        # No jobos.tenant_id set at all on this fresh connection.
        rows = await conn.fetch("SELECT * FROM applications WHERE id = $1", app_id)
        assert len(rows) == 0

async def test_empty_string_tenant_returns_zero_rows(db_pool: asyncpg.Pool, tenant_a_conn: asyncpg.Connection, tenant_a_id: uuid.UUID) -> None:
    app_id = uuid.uuid4()
    await tenant_a_conn.execute("INSERT INTO applications (id, user_id, path) VALUES ($1, $2, $3)", app_id, tenant_a_id, "Empty Tenant Test")

    async with db_pool.acquire() as conn:
        # is_local=false: these are separate implicit transactions, so a LOCAL
        # setting would be discarded before the SELECT below even runs.
        await conn.execute("SELECT set_config('jobos.tenant_id', '', false)")
        try:
            rows = await conn.fetch("SELECT * FROM applications WHERE id = $1", app_id)
            assert len(rows) == 0
        finally:
            await conn.execute("SELECT set_config('jobos.tenant_id', '', false)")

async def test_invalid_uuid_tenant_raises_error(db_pool: asyncpg.Pool) -> None:
    """A malformed (non-empty) tenant id must fail loudly, not silently
    degrade to "no tenant" and return zero rows."""
    async with db_pool.acquire() as conn:
        await conn.execute("SELECT set_config('jobos.tenant_id', 'not-a-uuid', false)")
        try:
            with pytest.raises(asyncpg.exceptions.InvalidTextRepresentationError):
                await conn.fetch("SELECT * FROM applications LIMIT 1")
        finally:
            await conn.execute("SELECT set_config('jobos.tenant_id', '', false)")
