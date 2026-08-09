"""3-touch referral email sequence."""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)

async def generate_referral_sequence(referrer: dict[str, Any], job: dict[str, Any], user_profile: dict[str, Any]) -> list[dict[str, str]]:
    """
    Returns 3 emails: [{"subject": str, "body": str, "send_delay_hours": int}].
    Touch 1 (Day 0): Warm intro citing shared connection.
    Touch 2 (Day 3): Value-add follow-up with relevant insight.
    Touch 3 (Day 6): Final gentle close.
    Personalization gate: drops low-quality emails (40-60% target drop rate).
    """
    logger.info("Generating referral sequence")
    # TODO: Implement LLM-based sequence generation and personalization gate
    return [
        {
            "subject": f"Connecting regarding {job.get('title', 'role')} at {job.get('company', 'your company')}",
            "body": "Warm intro body",
            "send_delay_hours": "0"
        },
        {
            "subject": "Quick follow-up",
            "body": "Value-add follow-up",
            "send_delay_hours": "72"
        },
        {
            "subject": "Final check",
            "body": "Gentle close",
            "send_delay_hours": "144"
        }
    ]
