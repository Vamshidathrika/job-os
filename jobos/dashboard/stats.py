"""Dashboard statistics retrieval."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def get_pipeline_stats(conn: Any, tenant_id: str) -> dict[str, Any]:
    """
    Get pipeline statistics for a tenant.

    Args:
        conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn); RLS
            confines every count below to this tenant's own rows.
        tenant_id: The tenant identifier, for logging.

    Returns:
        Dictionary with jobs_tracked, applications_sent, interviews_scheduled,
        offers_received, response_rate, avg_days_to_interview.
    """
    logger.info("fetching_pipeline_stats", tenant_id=tenant_id)

    row = await conn.fetchrow(
        """
        SELECT
            (SELECT count(*) FROM matches)                                   AS jobs_tracked,
            (SELECT count(*) FROM applications WHERE submitted_at IS NOT NULL) AS applications_sent,
            (SELECT count(*) FROM applications WHERE status = 'interview')   AS interviews_scheduled,
            (SELECT count(*) FROM applications WHERE status = 'offer')       AS offers_received,
            (SELECT count(*) FROM applications
              WHERE submitted_at IS NOT NULL
                AND status NOT IN ('pending', 'submitted'))                  AS responded,
            (SELECT avg(EXTRACT(EPOCH FROM (interview_scheduled_at - submitted_at)) / 86400)
               FROM applications
              WHERE interview_scheduled_at IS NOT NULL
                AND submitted_at IS NOT NULL)                                AS avg_days_to_interview
        """
    )

    applications_sent = row["applications_sent"] or 0
    responded = row["responded"] or 0
    # Guard the division: a tenant with nothing sent has no rate, not 0/0.
    response_rate = round(responded / applications_sent, 4) if applications_sent else 0.0
    avg_days = row["avg_days_to_interview"]

    return {
        "jobs_tracked": row["jobs_tracked"] or 0,
        "applications_sent": applications_sent,
        "interviews_scheduled": row["interviews_scheduled"] or 0,
        "offers_received": row["offers_received"] or 0,
        "response_rate": response_rate,
        "avg_days_to_interview": round(float(avg_days), 1) if avg_days is not None else None,
    }
