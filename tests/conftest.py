import os
import uuid
import pytest
import pytest_asyncio
import asyncpg
from typing import AsyncGenerator

from jobos.db.models import ALL_DDL
from jobos.db.rls import TENANT_TABLES, generate_rls_sql

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
    """Runs the schema creation SQL + RLS policies, and seeds the two fixed
    test tenants (users + tenants rows) that tenant_a_conn/tenant_b_conn rely on.

    A tenant's row id is set equal to its owning user's id — that's the
    app-level invariant that lets a single 'jobos.tenant_id' session var
    satisfy both the tenant_id-keyed tables (credentials, tenant_keys) and
    the user_id-keyed tables (applications, people, ...).
    """
    async with db_pool.acquire() as conn:
        # The app role is deliberately not a superuser (RLS never applies to
        # superusers, which would make every isolation test pass vacuously),
        # so it cannot CREATE EXTENSION. pgvector must already be installed
        # in the test database by a privileged role — see README setup.
        if not await conn.fetchval("SELECT 1 FROM pg_extension WHERE extname = 'vector'"):
            raise RuntimeError(
                "pgvector is not installed in the test database. Run: "
                "psql -d jobos_test -c 'CREATE EXTENSION vector;' as a superuser."
            )
        for ddl in ALL_DDL:
            await conn.execute(ddl)
        for table_name in TENANT_TABLES:
            for statement in generate_rls_sql(table_name):
                await conn.execute(statement)

        for tid, email in ((TENANT_A_ID, "tenant-a@test.jobos.local"), (TENANT_B_ID, "tenant-b@test.jobos.local")):
            # RLS is FORCEd even for the owning role, so a tenant can only
            # insert its own users/tenants row — set the session var (not
            # LOCAL, so it survives across these separate implicit
            # transactions) to that tenant before seeding it.
            await conn.execute("SELECT set_config('jobos.tenant_id', $1, false)", str(tid))
            await conn.execute(
                "INSERT INTO users (id, email) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING", tid, email
            )
            await conn.execute(
                "INSERT INTO tenants (id, user_id) VALUES ($1, $1) ON CONFLICT (id) DO NOTHING", tid
            )
        await conn.execute("SELECT set_config('jobos.tenant_id', '', false)")

@pytest_asyncio.fixture
async def tenant_a_conn(db_pool: asyncpg.Pool, setup_schema: None) -> AsyncGenerator[asyncpg.Connection, None]:
    """Connection with tenant_a context set.

    Must match the session var RLS policies actually check — jobos/db/rls.py
    uses 'jobos.tenant_id', NOT 'app.current_tenant'. And it must be set at
    session scope (is_local=false), not LOCAL: each test issues several
    separate statements on this connection with no enclosing transaction, and
    inserts need to commit individually so a *different* pooled connection
    (tenant_b_conn) can actually see them — a LOCAL setting would reset
    before the next statement and silently make every isolation check pass
    for the wrong reason (RLS sees no tenant at all, not "wrong tenant").
    """
    async with db_pool.acquire() as conn:
        await conn.execute("SELECT set_config('jobos.tenant_id', $1, false)", str(TENANT_A_ID))
        yield conn
        await conn.execute("SELECT set_config('jobos.tenant_id', '', false)")

@pytest_asyncio.fixture
async def tenant_b_conn(db_pool: asyncpg.Pool, setup_schema: None) -> AsyncGenerator[asyncpg.Connection, None]:
    """Connection with tenant_b context set."""
    async with db_pool.acquire() as conn:
        await conn.execute("SELECT set_config('jobos.tenant_id', $1, false)", str(TENANT_B_ID))
        yield conn
        await conn.execute("SELECT set_config('jobos.tenant_id', '', false)")

@pytest.fixture
def tenant_a_id() -> uuid.UUID:
    return TENANT_A_ID

@pytest.fixture
def tenant_b_id() -> uuid.UUID:
    return TENANT_B_ID

@pytest.fixture
def sample_credential() -> str:
    return "sk-or-v1-test-key-12345"
