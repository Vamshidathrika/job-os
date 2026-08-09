"""Ghost job / stale listing detector."""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)

async def detect_ghost_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect jobs that are likely ghost listings.
    
    A ghost job might be posted > 60 days ago, reposted multiple times,
    or have no response pattern.
    
    Args:
        jobs: A list of job listing dictionaries to analyze.
        
    Returns:
        List of flagged jobs, each containing a 'ghost_score' and 'reason'.
    """
    logger.info("Detecting ghost jobs", job_count=len(jobs))
    flagged_jobs = []
    
    for job in jobs:
        # Mock logic to determine if it's a ghost job
        # E.g., if 'days_active' > 60
        days_active = job.get("days_active", 0)
        if days_active > 60:
            job_copy = job.copy()
            job_copy["ghost_score"] = 0.8
            job_copy["reason"] = f"Posted {days_active} days ago (> 60 days)"
            flagged_jobs.append(job_copy)
            
    return flagged_jobs
