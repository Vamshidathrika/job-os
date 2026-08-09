"""Post-interview follow-up generation."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def generate_thank_you(
    interview: dict[str, Any], debrief: dict[str, Any]
) -> dict[str, Any]:
    """
    Generate a personalized thank-you email referencing specific discussion points from the debrief.
    
    Args:
        interview: The interview details.
        debrief: The structured post-interview debrief.
        
    Returns:
        dict[str, Any]: A dictionary containing 'subject', 'body', and 'send_delay_hours'.
    """
    logger.info("generating_thank_you_email")
    
    return {
        "subject": "Thank you for the great conversation!",
        "body": "I really enjoyed learning more about the team.",
        "send_delay_hours": 24
    }
