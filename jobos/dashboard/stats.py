"""Dashboard statistics retrieval."""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)


async def get_pipeline_stats(tenant_id: str) -> dict[str, Any]:
    """
    Get pipeline statistics for a tenant.
    
    Returns:
        Dictionary with jobs_tracked, applications_sent, interviews_scheduled,
        offers_received, response_rate, avg_days_to_interview.
    """
    logger.info("fetching_pipeline_stats", tenant_id=tenant_id)
    # Mock data for now
    return {
        "jobs_tracked": 120,
        "applications_sent": 45,
        "interviews_scheduled": 5,
        "offers_received": 1,
        "response_rate": 0.11,
        "avg_days_to_interview": 14.5
    }
