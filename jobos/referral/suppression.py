"""Global suppression list enforcement."""

from __future__ import annotations

import asyncpg
import structlog

from jobos.policy.compliance import hash_email_for_suppression

logger = structlog.get_logger(__name__)

async def check_suppression(conn: asyncpg.Connection, email: str) -> bool:
    """Returns True if email hash exists in global suppression table."""
    email_hash = hash_email_for_suppression(email)
    
    query = "SELECT 1 FROM suppression_list WHERE email_hash = $1"
    result = await conn.fetchval(query, email_hash)
    
    is_suppressed = result is not None
    if is_suppressed:
        logger.info("Email found in suppression list")
        
    return is_suppressed

async def add_to_suppression(conn: asyncpg.Connection, email: str) -> None:
    """Adds an email hash to the global suppression list."""
    email_hash = hash_email_for_suppression(email)
    
    query = "INSERT INTO suppression_list (email_hash) VALUES ($1) ON CONFLICT (email_hash) DO NOTHING"
    await conn.execute(query, email_hash)
    logger.info("Added email to suppression list")
