"""3-touch referral email sequence generator."""

from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion

from jobos.config import Settings, settings as default_settings

logger = structlog.get_logger(__name__)

TOUCH_DELAYS_HOURS = (0, 72, 144)

SYSTEM_PROMPT = """You write short, plain referral request emails from one working \
engineer to another.

Hard rules:
- Use ONLY facts given in the input. Never invent shared history, never claim to \
have analysed the company's product, tech stack, or metrics, and never invent \
mutual acquaintances.
- No flattery, no buzzwords, no exclamation marks.
- Each email under 120 words. Plain text. No markdown.
- Touch 1: introduce yourself, cite the real shared context, ask one specific question.
- Touch 2: brief follow-up that adds one genuinely useful thing from the sender's \
own experience.
- Touch 3: short close that makes it easy to say no.

Return ONLY a JSON array of exactly 3 objects with keys "subject" and "body"."""


def has_real_personalization(referrer: dict[str, Any]) -> bool:
    """Whether there is genuine, checkable common ground with this person.

    This is the personalization gate. Without real shared context an email is
    a cold pitch wearing a referral costume: it converts poorly and burns both
    the relationship and the sending domain's reputation. Dropping those is
    the intended behaviour, not a failure.
    """
    return bool(referrer.get("shared_school") or referrer.get("shared_past_company"))


async def generate_referral_sequence(
    referrer: dict[str, Any],
    job: dict[str, Any],
    user_profile: dict[str, Any],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """
    Returns 3 personalized referral emails: [{"subject": str, "body": str, "send_delay_hours": int}].
    Touch 1 (Day 0): Warm intro citing shared connection.
    Touch 2 (Day 3): Value-add follow-up with relevant insight.
    Touch 3 (Day 6): Final gentle close.
    Personalization gate: drops low-quality emails (40-60% target drop rate).

    Returns an empty list when the gate rejects the candidate, or when the
    model output cannot be validated — callers must treat "no sequence" as a
    normal outcome and skip the send.
    """
    settings = settings or default_settings
    ref_name = referrer.get("name") or "there"
    company = job.get("company") or referrer.get("company_domain") or "the team"
    role = job.get("title") or "the role"

    if not has_real_personalization(referrer):
        logger.info(
            "referral_sequence_dropped_by_gate",
            referrer=ref_name,
            company=company,
            reason="no_shared_context",
        )
        return []

    prompt = _build_prompt(referrer, job, user_profile, ref_name, company, role)

    try:
        response: Any = await acompletion(
            model=settings.llm.tailoring_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        raw = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(
            "referral_sequence_generation_failed",
            referrer=ref_name,
            company=company,
            error=str(e),
        )
        return []

    touches = _parse_touches(raw)
    if touches is None:
        logger.error("referral_sequence_unparseable", referrer=ref_name, company=company)
        return []

    logger.info("referral_sequence_generated", referrer=ref_name, company=company, touches=len(touches))
    return touches


def _build_prompt(
    referrer: dict[str, Any],
    job: dict[str, Any],
    user_profile: dict[str, Any],
    ref_name: str,
    company: str,
    role: str,
) -> str:
    """Assemble the fact sheet the model is allowed to draw from."""
    shared_school = ", ".join(referrer.get("shared_school") or []) or "none"
    shared_company = ", ".join(referrer.get("shared_past_company") or []) or "none"
    facts = {
        "recipient_name": ref_name,
        "recipient_title": referrer.get("title") or "unknown",
        "company": company,
        "role_applied_for": role,
        "sender_name": user_profile.get("name") or "the sender",
        "sender_current_title": user_profile.get("title") or "unknown",
        "sender_years_experience": user_profile.get("yoe") or "unknown",
        "shared_school": shared_school,
        "shared_past_company": shared_company,
    }
    return (
        "Write the 3-touch sequence using only these facts:\n"
        + json.dumps(facts, indent=2)
        + "\n\nThe shared_school / shared_past_company values are the only common "
        "ground you may cite. If both are 'none', do not imply any connection."
    )


def _parse_touches(raw: str) -> list[dict[str, Any]] | None:
    """Validate the model's JSON into exactly three well-formed touches."""
    text = str(raw).strip()
    # Models often wrap JSON in a ```json fence despite instructions.
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return None

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, list) or len(parsed) != len(TOUCH_DELAYS_HOURS):
        return None

    touches = []
    # strict=True is safe here: length was just checked against TOUCH_DELAYS_HOURS.
    for item, delay in zip(parsed, TOUCH_DELAYS_HOURS, strict=True):
        if not isinstance(item, dict):
            return None
        subject = str(item.get("subject") or "").strip()
        body = str(item.get("body") or "").strip()
        if not subject or not body:
            return None
        touches.append({"subject": subject, "body": body, "send_delay_hours": delay})
    return touches
