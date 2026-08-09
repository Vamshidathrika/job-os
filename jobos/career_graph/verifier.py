"""Verifier pipeline for Career Graph bullets."""

from __future__ import annotations

from typing import Any
import structlog
import asyncpg

logger = structlog.get_logger(__name__)

async def get_verification_queue(conn: asyncpg.Connection, user_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """
    Returns top bullets ranked by retrieval_count DESC for the initial 5-minute activation ladder.
    
    Args:
        conn: The database connection.
        user_id: The ID of the user.
        limit: Max number of bullets to retrieve.
        
    Returns:
        List of bullet dictionaries.
    """
    logger.info("fetching_verification_queue", user_id=user_id, limit=limit)
    query = """
        SELECT id, company, role, bullet_text, metric, evidence_url, verification_status, retrieval_count
        FROM cg_bullets
        WHERE user_id = $1 AND verification_status = 'unverified'
        ORDER BY retrieval_count DESC
        LIMIT $2
    """
    records = await conn.fetch(query, user_id, limit)
    return [dict(r) for r in records]

async def verify_bullet(conn: asyncpg.Connection, bullet_id: str, verified: bool) -> None:
    """
    Updates verification_status to 'verified' or 'failed'.
    
    Args:
        conn: The database connection.
        bullet_id: The ID of the bullet.
        verified: Whether the verification was successful.
    """
    logger.info("verifying_bullet", bullet_id=bullet_id, verified=verified)
    status = "verified" if verified else "failed"
    query = "UPDATE cg_bullets SET verification_status = $1 WHERE id = $2"
    await conn.execute(query, status, bullet_id)
