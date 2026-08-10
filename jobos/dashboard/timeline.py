"""Activity timeline retrieval."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

MAX_TIMELINE_ROWS = 200


async def get_activity_timeline(
    conn: Any, tenant_id: str, days: int = 30
) -> list[dict[str, Any]]:
    """
    Get chronological list of all actions taken by the system.

    Args:
        conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn).
        tenant_id: The tenant identifier, for logging.
        days: Number of days to look back.

    Returns:
        List of chronological actions, newest first.
    """
    logger.info("fetching_activity_timeline", tenant_id=tenant_id, days=days)

    rows = await conn.fetch(
        """
        SELECT id, type, timestamp, company, role FROM (
            SELECT a.id,
                   CASE WHEN a.status = 'offer'     THEN 'offer_received'
                        WHEN a.status = 'interview' THEN 'interview_scheduled'
                        WHEN a.status = 'rejected'  THEN 'application_rejected'
                        ELSE 'application_submitted' END AS type,
                   COALESCE(a.submitted_at, a.created_at) AS timestamp,
                   c.name  AS company,
                   j.title AS role
              FROM applications a
              LEFT JOIN jobs j      ON j.id = a.job_id
              LEFT JOIN companies c ON c.id = j.company_id
             WHERE COALESCE(a.submitted_at, a.created_at) > now() - make_interval(days => $1)

            UNION ALL

            SELECT q.id,
                   q.action_type AS type,
                   q.created_at  AS timestamp,
                   q.payload->>'company' AS company,
                   q.payload->>'role'    AS role
              FROM action_queue q
             WHERE q.status = 'completed'
               AND q.created_at > now() - make_interval(days => $1)
        ) events
        ORDER BY timestamp DESC
        LIMIT $2
        """,
        days,
        MAX_TIMELINE_ROWS,
    )

    return [
        {
            "id": str(row["id"]),
            "type": row["type"],
            "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
            "details": {"company": row["company"], "role": row["role"]},
        }
        for row in rows
    ]
