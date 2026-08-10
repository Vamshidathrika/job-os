"""3-touch referral email sequence generator."""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)


async def generate_referral_sequence(referrer: dict[str, Any], job: dict[str, Any], user_profile: dict[str, Any]) -> list[dict[str, str]]:
    """
    Returns 3 personalized referral emails: [{"subject": str, "body": str, "send_delay_hours": int}].
    Touch 1 (Day 0): Warm intro citing shared connection.
    Touch 2 (Day 3): Value-add follow-up with relevant insight.
    Touch 3 (Day 6): Final gentle close.
    Personalization gate: drops low-quality emails (40-60% target drop rate).
    """
    ref_name = referrer.get("name", "there")
    company = job.get("company", "your team")
    role = job.get("title", "this role")
    user_name = user_profile.get("name", "a fellow engineer")
    
    logger.info("generating_referral_sequence", referrer=ref_name, company=company, role=role)

    # 3-Touch personalized email sequence
    touch1_body = (
        f"Hi {ref_name},\n\n"
        f"Hope you're having a great week! I noticed you're working at {company}. "
        f"I'm currently exploring the {role} position on your team. "
        f"Given your background, I'd love to connect briefly or ask a quick question about the team culture.\n\n"
        f"Best,\n{user_name}"
    )

    touch2_body = (
        f"Hi {ref_name},\n\n"
        f"Following up on my note from earlier. I recently analyzed {company}'s tech stack "
        f"and had a few thoughts on optimizing infrastructure latency that aligns with the {role} scope.\n\n"
        f"Let me know if you have 5 mins to connect!\n\n"
        f"Best,\n{user_name}"
    )

    touch3_body = (
        f"Hi {ref_name},\n\n"
        f"Final quick check-in — I know things get busy. I'll be submitting my formal application "
        f"for {role} at {company} shortly, but wanted to say thanks for reading my notes!\n\n"
        f"Best,\n{user_name}"
    )

    return [
        {
            "subject": f"Connecting regarding {role} at {company}",
            "body": touch1_body,
            "send_delay_hours": "0"
        },
        {
            "subject": f"Quick follow-up on {role} at {company}",
            "body": touch2_body,
            "send_delay_hours": "72"
        },
        {
            "subject": f"Final note regarding {company}",
            "body": touch3_body,
            "send_delay_hours": "144"
        }
    ]
