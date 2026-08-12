"""Profile optimization module."""
from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion

from jobos.config import Settings, settings as default_settings
from jobos.profile.keyword_extractor import extract_target_keywords

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You audit a LinkedIn profile for a candidate targeting specific roles.

Rules:
- Judge only what is in the supplied profile. Never assume unstated experience.
- Every suggestion must name the section it applies to and be concrete enough
  to act on in one edit.
- Headline options must be under 220 characters and must not claim skills the
  profile does not evidence.

Return ONLY JSON:
{"score": <0-100>, "suggestions": [{"section": "", "suggestion": ""}],
 "headline_options": [""]}"""

# Terms mentioned in at least this share of target JDs are worth having on a
# profile; below that they are noise from one or two postings.
KEYWORD_GAP_MIN_FREQUENCY = 0.5


async def analyze_profile(
    profile_data: dict[str, Any],
    target_job_descriptions: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Analyze a LinkedIn profile and provide optimization suggestions.

    WHAT: Evaluates headline, summary, and experience against best practices and target roles.
    WHY: To maximize a user's visibility and conversion rate for inbound recruiter outreach.

    Keyword gaps are computed directly from the target job descriptions rather
    than guessed, so they reflect what employers actually asked for.
    """
    settings = settings or default_settings
    logger.info("analyzing_profile", profile_keys=list(profile_data.keys()))

    keyword_gaps = _keyword_gaps(profile_data, target_job_descriptions or [])

    analysis = await _llm_analysis(profile_data, keyword_gaps, settings)
    if analysis is None:
        # Structural fallback: still useful, and never invents a score.
        logger.warning("profile_llm_analysis_failed_using_structural_fallback")
        analysis = _structural_analysis(profile_data)

    analysis["keyword_gaps"] = keyword_gaps
    return analysis


def _keyword_gaps(profile_data: dict[str, Any], job_descriptions: list[str]) -> list[str]:
    """Terms common in target roles but absent from the profile text."""
    if not job_descriptions:
        return []

    profile_text = json.dumps(profile_data).lower()
    demanded = extract_target_keywords(job_descriptions)
    return [
        term
        for term, frequency in demanded.items()
        if frequency >= KEYWORD_GAP_MIN_FREQUENCY and term not in profile_text
    ]


async def _llm_analysis(
    profile_data: dict[str, Any], keyword_gaps: list[str], settings: Settings
) -> dict[str, Any] | None:
    """Ask the model to score the profile; None when unusable."""
    try:
        response: Any = await acompletion(
            model=settings.llm.tailoring_model,
            api_key=settings.llm.platform_groq_key or None,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"PROFILE:\n{json.dumps(profile_data, indent=2)}\n\n"
                        f"KEYWORDS MISSING VS TARGET ROLES: {keyword_gaps or 'none'}"
                    ),
                },
            ],
            temperature=0.3,
        )
        raw = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("profile_analysis_failed", error=str(e))
        return None

    payload = _parse_json_object(raw)
    if payload is None:
        return None

    try:
        raw_score = payload.get("score")
        score = float(raw_score) if raw_score is not None else -1.0
    except (TypeError, ValueError):
        return None
    if not 0 <= score <= 100:
        return None

    suggestions = payload.get("suggestions")
    if not isinstance(suggestions, list):
        return None

    headline_options = payload.get("headline_options")
    return {
        "score": score,
        "suggestions": [s for s in suggestions if isinstance(s, dict)],
        "headline_options": [str(h) for h in headline_options]
        if isinstance(headline_options, list)
        else [],
    }


def _structural_analysis(profile_data: dict[str, Any]) -> dict[str, Any]:
    """Deterministic completeness check used when the model is unavailable.

    Scores only what can be verified — presence and length of each section —
    so a degraded run reports a real (if blunt) number rather than a fake one.
    """
    checks = {
        "headline": bool(str(profile_data.get("headline") or "").strip()),
        "summary": len(str(profile_data.get("summary") or "").strip()) >= 200,
        "experience": bool(profile_data.get("experience")),
        "skills": bool(profile_data.get("skills")),
    }
    score = round(100 * sum(checks.values()) / len(checks), 1)

    advice = {
        "headline": "Add a headline naming your target role and core stack.",
        "summary": "Expand the summary to at least 200 characters with concrete outcomes.",
        "experience": "Add at least one role with measurable achievements.",
        "skills": "List the skills your target roles ask for.",
    }
    return {
        "score": score,
        "suggestions": [
            {"section": section, "suggestion": advice[section]}
            for section, ok in checks.items()
            if not ok
        ],
        "headline_options": [],
    }


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
