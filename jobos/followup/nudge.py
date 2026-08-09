"""Graceful status nudge generator."""
from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)

async def generate_status_nudge(interview: dict[str, Any], days_since: int) -> dict[str, str]:
    """
    Generate a status check-in message.
    
    Args:
        interview: Dictionary containing interview details.
        days_since: Number of days since the interview.
        
    Returns:
        Dictionary containing 'subject' and 'body' of the nudge.
    """
    logger.info("generating_status_nudge", interview_id=interview.get("id"), days_since=days_since)
    
    company = interview.get("company_name", "the company")
    role = interview.get("role_title", "the role")
    
    subject = f"Following up: Interview for {role} at {company}"
    body = (
        f"Hi there,\n\n"
        f"I hope this email finds you well. I'm checking in on the {role} position. "
        f"It's been {days_since} days since our interview, and I remain very interested "
        f"in the opportunity to join {company}. Please let me know if there's any update "
        f"or if you need any further information from my side.\n\n"
        f"Best regards,\n"
    )
    
    return {
        "subject": subject,
        "body": body
    }
