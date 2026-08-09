"""Post-interview debrief capture."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def capture_debrief(interview_id: str, notes: dict[str, Any]) -> dict[str, Any]:
    """
    Capture post-interview debrief details.
    
    Args:
        interview_id: The ID of the interview.
        notes: User's notes and thoughts from the interview.
        
    Returns:
        dict[str, Any]: Structured debrief containing sentiment, follow_up_actions, and likelihood_score.
    """
    logger.info("capturing_debrief", interview_id=interview_id)
    
    return {
        "sentiment": "neutral",
        "follow_up_actions": [],
        "likelihood_score": 0.0
    }
