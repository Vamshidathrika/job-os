"""Evidence tracking and fetching operations for Career Graph."""

from __future__ import annotations

import uuid
from typing import Any
import structlog
import asyncpg

logger = structlog.get_logger(__name__)

async def add_bullet(
    conn: asyncpg.Connection, 
    user_id: str, 
    company: str, 
    role: str, 
    bullet_text: str, 
    metric: str | None, 
    evidence_url: str
) -> str:
    """
    Adds a new career graph bullet to the database.
    
    Args:
        conn: The database connection.
        user_id: The ID of the user.
        company: The company name.
        role: The role name.
        bullet_text: The main text of the bullet.
        metric: An optional metric extracted.
        evidence_url: The URL proving the evidence.
        
    Returns:
        The ID of the newly inserted bullet.
    """
    bullet_id = str(uuid.uuid4())
    logger.info("adding_bullet", user_id=user_id, bullet_id=bullet_id, company=company)
    query = """
        INSERT INTO cg_bullets (
            id, user_id, company, role, bullet_text, metric, evidence_url, verification_status, retrieval_count
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, 'unverified', 0
        )
    """
    await conn.execute(query, bullet_id, user_id, company, role, bullet_text, metric, evidence_url)
    return bullet_id

async def fetch_retrieved_bullets(
    conn: asyncpg.Connection, 
    user_id: str, 
    job_requirements: dict[str, Any], 
    limit: int = 15
) -> list[dict[str, Any]]:
    """
    Fetches relevant bullets for job requirements and increments retrieval_count.
    
    Args:
        conn: The database connection.
        user_id: The ID of the user.
        job_requirements: Dictionary defining the job requirements.
        limit: Max number of bullets to fetch.
        
    Returns:
        List of retrieved bullet dictionaries.
    """
    logger.info("fetching_retrieved_bullets", user_id=user_id, limit=limit)
    
    # In a full system, this would involve semantic search or filtering based on job_requirements.
    # Here we fetch the most recent relevant items and increment retrieval_count as requested.
    query = """
        WITH selected AS (
            SELECT id
            FROM cg_bullets
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        ),
        updated AS (
            UPDATE cg_bullets
            SET retrieval_count = retrieval_count + 1
            WHERE id IN (SELECT id FROM selected)
            RETURNING id, company, role, bullet_text, metric, evidence_url, verification_status, retrieval_count
        )
        SELECT * FROM updated
    """
    records = await conn.fetch(query, user_id, limit)
    return [dict(r) for r in records]
