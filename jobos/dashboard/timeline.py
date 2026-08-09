"""Activity timeline retrieval."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone, timedelta
import structlog

logger = structlog.get_logger(__name__)


async def get_activity_timeline(tenant_id: str, days: int = 30) -> list[dict[str, Any]]:
    """
    Get chronological list of all actions taken by the system.
    
    Args:
        tenant_id: The tenant identifier.
        days: Number of days to look back.
    
    Returns:
        List of chronological actions.
    """
    logger.info("fetching_activity_timeline", tenant_id=tenant_id, days=days)
    
    now = datetime.now(timezone.utc)
    # Mock data for now
    return [
        {
            "id": "act-1",
            "type": "application_submitted",
            "timestamp": (now - timedelta(days=2)).isoformat(),
            "details": {"company": "Acme Corp", "role": "Software Engineer"}
        },
        {
            "id": "act-2",
            "type": "interview_scheduled",
            "timestamp": (now - timedelta(days=1)).isoformat(),
            "details": {"company": "Globex", "role": "Backend Engineer"}
        }
    ]
