"""Data structures and signal processor for pre-posting hiring signals."""

from __future__ import annotations

import datetime
from enum import Enum

import asyncpg
import structlog
from pydantic import BaseModel

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


async def process_signals(signals: list[HiringSignal], pool: asyncpg.Pool) -> None:
    """
    Process detected hiring signals.

    This function adds the company to the global `companies` table (if not exists)
    and updates the `tenant_company_universe` for relevant tenants based on the signal.

    Args:
        signals: A list of detected HiringSignal instances.
        pool: The asyncpg connection pool to use for database operations.
    """
    if not signals:
        logger.debug("No signals to process")
        return

    logger.info("Processing hiring signals", count=len(signals))

    async with pool.acquire() as conn:
        async with conn.transaction():
            for signal in signals:
                logger.debug(
                    "Processing individual signal",
                    company=signal.company_name,
                    signal_type=signal.signal_type.value,
                    confidence=signal.confidence,
                )

                # 1. Upsert company in global `companies` table
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

                # 2. Update `tenant_company_universe` for relevant tenants
                # This would typically join against tenant preferences/ICP
                await conn.execute(
                    """
                    INSERT INTO tenant_company_universe (tenant_id, company_domain, signal_type, action, added_at)
                    SELECT t.id, $1, $2, $3, NOW()
                    FROM tenants t
                    ON CONFLICT (tenant_id, company_domain) DO UPDATE
                    SET signal_type = $2, action = $3
                    """,
                    signal.company_domain,
                    signal.signal_type.value,
                    signal.action,
                )
