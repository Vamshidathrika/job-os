"""Database connection pool and tenant context manager."""

import contextlib
from typing import Any, AsyncGenerator
import asyncpg

from jobos.config import Settings


async def create_pool(settings: Settings) -> asyncpg.Pool:
    """Create an asyncpg connection pool.

    Args:
        settings: The root application settings.

    Returns:
        asyncpg.Pool: The connection pool.
    """
    pool = await asyncpg.create_pool(
        dsn=settings.db.dsn,
        min_size=settings.db.min_pool_size,
        max_size=settings.db.max_pool_size,
    )
    if not pool:
        raise RuntimeError("Failed to create asyncpg pool")
    return pool


@contextlib.asynccontextmanager
async def tenant_conn(pool: asyncpg.Pool, tenant_id: str) -> AsyncGenerator[Any, None]:
    """Acquire a tenant-isolated connection from the pool.

    This acquires a connection, starts a transaction, and sets the jobos.tenant_id
    configuration parameter. On completion, the transaction is committed or rolled back.

    Args:
        pool: The connection pool.
        tenant_id: The UUID of the tenant to isolate.

    Yields:
        asyncpg.Connection: The isolated connection inside a transaction.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Use parameterized set_config — NEVER f-string a tenant_id into SQL.
            # The 'true' arg to set_config makes it LOCAL (transaction-scoped).
            await conn.execute(
                "SELECT set_config('jobos.tenant_id', $1, true)",
                str(tenant_id),
            )
            yield conn


@contextlib.asynccontextmanager
async def global_conn(pool: asyncpg.Pool) -> AsyncGenerator[Any, None]:
    """Acquire a global, non-isolated connection from the pool.

    Args:
        pool: The connection pool.

    Yields:
        asyncpg.Connection: The connection.
    """
    async with pool.acquire() as conn:
        yield conn
