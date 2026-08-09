import os
import uuid
import pytest
import pytest_asyncio
import asyncpg
from typing import AsyncGenerator

# Use env var or default for test db
TEST_DB_DSN = os.environ.get("JOBOS_TEST_DB_DSN", "postgresql://jobos:jobos_dev@localhost:5432/jobos_test")

# Fixed UUIDs for cross-tenant testing
TENANT_A_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

@pytest_asyncio.fixture(scope="session")
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """Creates a test asyncpg pool to a test database."""
    pool = await asyncpg.create_pool(dsn=TEST_DB_DSN)
    if pool is None:
        raise RuntimeError("Failed to create asyncpg pool")
    yield pool
    await pool.close()

@pytest_asyncio.fixture(scope="session")
async def setup_schema(db_pool: asyncpg.Pool) -> None:
    """Runs the schema creation SQL + RLS policies."""
    # To be implemented by DB engineer
    pass

@pytest_asyncio.fixture
async def tenant_a_conn(db_pool: asyncpg.Pool, setup_schema: None) -> AsyncGenerator[asyncpg.Connection, None]:
    """Connection with tenant_a context set."""
    async with db_pool.acquire() as conn:
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(TENANT_A_ID))
        yield conn
        # Reset tenant context
        await conn.execute("SELECT set_config('app.current_tenant', '', true)")

@pytest_asyncio.fixture
async def tenant_b_conn(db_pool: asyncpg.Pool, setup_schema: None) -> AsyncGenerator[asyncpg.Connection, None]:
    """Connection with tenant_b context set."""
    async with db_pool.acquire() as conn:
        await conn.execute("SELECT set_config('app.current_tenant', $1, true)", str(TENANT_B_ID))
        yield conn
        # Reset tenant context
        await conn.execute("SELECT set_config('app.current_tenant', '', true)")

@pytest.fixture
def tenant_a_id() -> uuid.UUID:
    return TENANT_A_ID

@pytest.fixture
def tenant_b_id() -> uuid.UUID:
    return TENANT_B_ID

@pytest.fixture
def sample_credential() -> str:
    return "sk-or-v1-test-key-12345"
