"""Ghost job / stale listing detector."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

STALE_DAYS_THRESHOLD = 60
# Applications sent with no reply at all before we distrust the listing.
SILENT_APPLICATIONS_THRESHOLD = 3
GHOST_SCORE_FLAG_THRESHOLD = 0.5


async def detect_ghost_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect jobs that are likely ghost listings.

    A ghost job might be posted > 60 days ago, reposted multiple times,
    or have no response pattern.

    Args:
        jobs: A list of job listing dictionaries to analyze.

    Returns:
        List of flagged jobs, each containing a 'ghost_score' and 'reason'.
    """
    logger.info("detecting_ghost_jobs", job_count=len(jobs))

    flagged = []
    for job in jobs:
        score, reasons = _score_job(job)
        if score >= GHOST_SCORE_FLAG_THRESHOLD:
            job_copy = dict(job)
            job_copy["ghost_score"] = round(score, 2)
            job_copy["reason"] = "; ".join(reasons)
            flagged.append(job_copy)

    logger.info("ghost_jobs_flagged", flagged=len(flagged), total=len(jobs))
    return flagged


async def detect_ghost_jobs_from_db(conn: Any, limit: int = 500) -> list[dict[str, Any]]:
    """Score listings using real signal from the database.

    Combines listing age with the tenant's own application history: a posting
    that has swallowed several applications without a single reply is far more
    suspicious than one that is merely old.
    """
    rows = await conn.fetch(
        """
        SELECT j.id,
               j.title,
               j.first_seen_at,
               EXTRACT(EPOCH FROM (now() - j.first_seen_at)) / 86400 AS days_active,
               count(a.id) FILTER (WHERE a.submitted_at IS NOT NULL)  AS applications_sent,
               count(a.id) FILTER (WHERE a.status NOT IN ('pending', 'submitted')) AS responses
          FROM jobs j
          LEFT JOIN applications a ON a.job_id = j.id
         GROUP BY j.id, j.title, j.first_seen_at
         LIMIT $1
        """,
        limit,
    )

    jobs = [
        {
            "id": str(row["id"]),
            "title": row["title"],
            "days_active": float(row["days_active"] or 0),
            "applications_sent": row["applications_sent"] or 0,
            "responses": row["responses"] or 0,
        }
        for row in rows
    ]
    return await detect_ghost_jobs(jobs)


def _score_job(job: dict[str, Any]) -> tuple[float, list[str]]:
    """Compute a ghost score and the human-readable reasons behind it."""
    score = 0.0
    reasons: list[str] = []

    days_active = _days_active(job)
    if days_active > STALE_DAYS_THRESHOLD:
        score += 0.8
        reasons.append(f"Posted {int(days_active)} days ago (> {STALE_DAYS_THRESHOLD} days)")

    repost_count = int(job.get("repost_count") or 0)
    if repost_count >= 2:
        score += 0.3
        reasons.append(f"Reposted {repost_count} times")

    applications_sent = int(job.get("applications_sent") or 0)
    responses = int(job.get("responses") or 0)
    if applications_sent >= SILENT_APPLICATIONS_THRESHOLD and responses == 0:
        score += 0.5
        reasons.append(f"{applications_sent} applications sent, zero responses")

    return min(score, 1.0), reasons


def _days_active(job: dict[str, Any]) -> float:
    """Listing age in days, from an explicit field or first_seen_at."""
    if job.get("days_active") is not None:
        return float(job["days_active"])

    first_seen = job.get("first_seen_at")
    if isinstance(first_seen, datetime):
        reference = first_seen if first_seen.tzinfo else first_seen.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - reference).total_seconds() / 86400
    return 0.0
