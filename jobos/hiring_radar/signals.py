"""Data structures and signal processor for pre-posting hiring signals."""

from __future__ import annotations

import datetime
from enum import Enum

import asyncpg
import structlog
from pydantic import BaseModel

from jobos.db.pool import tenant_conn

logger = structlog.get_logger(__name__)


class SignalType(Enum):
    """The type of pre-posting hiring signal detected."""

    FUNDING = "FUNDING"
    VELOCITY_SPIKE = "VELOCITY_SPIKE"
    EXEC_DEPARTURE = "EXEC_DEPARTURE"
    PRODUCT_LAUNCH = "PRODUCT_LAUNCH"


class HiringSignal(BaseModel):
    """A detected pre-posting hiring signal for a company."""

    company_name: str
    company_domain: str
    signal_type: SignalType
    prediction: str
    action: str
    confidence: float
    detected_at: datetime.datetime


async def process_signals(
    signals: list[HiringSignal], pool: asyncpg.Pool, tenant_ids: list[str]
) -> int:
    """
    Process detected hiring signals.

    This function adds the company to the global `companies` table (if not exists)
    and updates the `tenant_company_universe` for the given tenants.

    Target tenants must be passed in explicitly. The previous version selected
    them with `INSERT ... SELECT t.id FROM tenants`, which runs under FORCE
    row-level security: a global worker holds no tenant context, so that
    SELECT matched zero rows and the statement silently inserted nothing
    while still reporting success.

    Args:
        signals: A list of detected HiringSignal instances.
        pool: The asyncpg connection pool to use for database operations.
        tenant_ids: The tenants whose universe should receive these signals.

    Returns:
        The number of (signal, tenant) rows written.
    """
    if not signals:
        logger.debug("No signals to process")
        return 0

    if not tenant_ids:
        logger.warning("No target tenants supplied; hiring signals would be discarded")
        return 0

    logger.info("Processing hiring signals", count=len(signals), tenants=len(tenant_ids))
    written = 0

    async with pool.acquire() as conn:
        async with conn.transaction():
            for signal in signals:
                logger.debug(
                    "Processing individual signal",
                    company=signal.company_name,
                    signal_type=signal.signal_type.value,
                    confidence=signal.confidence,
                )

                # 1. Upsert company in the global `companies` table. This one
                # has no RLS, so it is safe on an unscoped connection.
                await conn.execute(
                    """
                    INSERT INTO companies (name, domain, created_at, updated_at)
                    VALUES ($1, $2, NOW(), NOW())
                    ON CONFLICT (domain) DO UPDATE
                    SET updated_at = NOW()
                    """,
                    signal.company_name,
                    signal.company_domain,
                )

    # 2. Write each tenant's universe row under that tenant's own RLS context.
    for tenant_id in tenant_ids:
        async with tenant_conn(pool, tenant_id) as conn:
            for signal in signals:
                status = await conn.execute(
                    """
                    INSERT INTO tenant_company_universe (tenant_id, company_domain, signal_type, action, added_at)
                    VALUES ($1::uuid, $2, $3, $4, NOW())
                    ON CONFLICT (tenant_id, company_domain) DO UPDATE
                    SET signal_type = EXCLUDED.signal_type,
                        action = EXCLUDED.action,
                        added_at = EXCLUDED.added_at
                    """,
                    tenant_id,
                    signal.company_domain,
                    signal.signal_type.value,
                    signal.action,
                )
                written += _rows_affected(status)

    if not written:
        logger.error(
            "hiring_signals_written_nothing", signals=len(signals), tenants=len(tenant_ids)
        )
    logger.info("hiring_signals_processed", rows_written=written)
    return written


def _rows_affected(status: str) -> int:
    """Parse the row count out of an asyncpg command status like 'INSERT 0 1'."""
    parts = str(status).split()
    return int(parts[-1]) if parts and parts[-1].isdigit() else 0
