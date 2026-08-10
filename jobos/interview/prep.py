"""Interview preparation generator."""

from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion

from jobos.config import Settings, settings as default_settings

logger = structlog.get_logger(__name__)

EMPTY_PREP_PACK: dict[str, Any] = {
    "company_research": {"key_facts": [], "recent_news": [], "culture_insights": []},
    "likely_questions": [],
    "answer_frameworks": [],
    "technical_topics": [],
    "questions_to_ask": [],
}

SYSTEM_PROMPT = """You prepare a candidate for a specific interview.

Ground every output in the supplied job description and candidate profile.

Hard rules:
- Do NOT state facts about the company (funding, headcount, news, culture)
  unless they appear in the supplied COMPANY CONTEXT. If none is supplied,
  return empty lists for company_research. Inventing company facts would send
  the candidate into the room repeating something untrue.
- Answer frameworks must be built from the candidate's own listed experience.
  Never invent achievements, employers or metrics for them.
- Technical topics must be drawn from the job description.

Return ONLY JSON:
{"company_research": {"key_facts": [""], "recent_news": [""], "culture_insights": [""]},
 "likely_questions": [""],
 "answer_frameworks": [{"question": "", "framework": "", "uses_experience": ""}],
 "technical_topics": [""],
 "questions_to_ask": [""]}"""


async def generate_prep_pack(
    job: dict[str, Any],
    user_profile: dict[str, Any],
    interview_type: str,
    company_context: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Generate a comprehensive interview prep pack.

    Args:
        job: The job description and details.
        user_profile: The user's verified profile data.
        interview_type: Type of interview (e.g., 'phone_screen', 'technical', 'behavioral',
            'system_design', 'hiring_manager', 'panel').
        company_context: Researched company facts. Company research is left
            empty when this is absent rather than invented.
        settings: Application settings; defaults to the global singleton.

    Returns:
        dict[str, Any]: Comprehensive prep including company_research, likely_questions,
            answer_frameworks, technical_topics, and questions_to_ask.
            Returns the empty pack if generation fails — the candidate is
            better served by a visibly empty pack than a confident wrong one.
    """
    settings = settings or default_settings
    logger.info("generating_prep_pack", interview_type=interview_type)

    prompt = (
        f"INTERVIEW TYPE: {interview_type}\n\n"
        f"JOB:\n{json.dumps(job, indent=2, default=str)}\n\n"
        f"CANDIDATE PROFILE:\n{json.dumps(user_profile, indent=2, default=str)}\n\n"
        f"COMPANY CONTEXT:\n{company_context.strip() if company_context else 'none supplied'}"
    )

    try:
        response: Any = await acompletion(
            model=settings.llm.tailoring_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        raw = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("prep_pack_generation_failed", interview_type=interview_type, error=str(e))
        return _empty_pack()

    payload = _parse_json_object(raw)
    if payload is None:
        logger.error("prep_pack_unparseable", interview_type=interview_type)
        return _empty_pack()

    pack = _coerce_pack(payload)

    if not company_context:
        # Belt and braces: strip anything the model asserted about the company
        # despite being told there was no source for it.
        invented = any(pack["company_research"].values())
        if invented:
            logger.warning("prep_pack_dropped_unsourced_company_research")
        pack["company_research"] = dict(EMPTY_PREP_PACK["company_research"])

    logger.info(
        "prep_pack_generated",
        interview_type=interview_type,
        questions=len(pack["likely_questions"]),
        topics=len(pack["technical_topics"]),
    )
    return pack


def _empty_pack() -> dict[str, Any]:
    """A fresh copy of the empty structure (never share the module-level dict)."""
    return {
        "company_research": dict(EMPTY_PREP_PACK["company_research"]),
        "likely_questions": [],
        "answer_frameworks": [],
        "technical_topics": [],
        "questions_to_ask": [],
    }


def _coerce_pack(payload: dict[str, Any]) -> dict[str, Any]:
    """Force the model's reply into the documented shape."""
    pack = _empty_pack()

    research = payload.get("company_research")
    if isinstance(research, dict):
        for key in pack["company_research"]:
            value = research.get(key)
            if isinstance(value, list):
                pack["company_research"][key] = [str(v) for v in value if str(v).strip()]

    for key in ("likely_questions", "technical_topics", "questions_to_ask"):
        value = payload.get(key)
        if isinstance(value, list):
            pack[key] = [str(v) for v in value if str(v).strip()]

    frameworks = payload.get("answer_frameworks")
    if isinstance(frameworks, list):
        pack["answer_frameworks"] = [f for f in frameworks if isinstance(f, dict)]

    return pack


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """Parse a JSON object from a model reply, tolerating code fences."""
    text = str(raw).strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
