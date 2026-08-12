"""JD-specific resume tailoring module."""

from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion

from jobos.config import Settings

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You assemble a tailored resume from a fixed set of pre-verified \
bullet points.

Absolute rules:
- You may ONLY use bullets from the supplied list. Reproduce each selected \
bullet's text essentially verbatim; light rewording for flow is allowed, but you \
must not add any claim, metric, technology, employer, or date that is not already \
in that bullet.
- Never invent or embellish. If the job description asks for something no bullet \
supports, omit it rather than inventing it.
- Select and order the bullets that best match the job description. Prefer fewer, \
stronger bullets over padding.

Return ONLY a JSON object:
{"used_bullet_ids": ["<id>", ...], "tailored_text": "<the resume body>"}"""


async def generate_tailored_resume(
    job_description: str,
    verified_bullets: list[dict[str, Any]],
    settings: Settings,
) -> dict[str, Any]:
    """
    Generates tailored resume containing ONLY bullets from `verified_bullets`.

    Args:
        job_description: The job description text.
        verified_bullets: List of bullet point dictionaries that are verified.
        settings: Application settings.

    Returns:
        Dictionary containing 'tailored_text' and 'used_bullet_ids'.
        Both are empty when there is nothing verified to work from or when the
        model's output fails validation — an unverifiable resume must never be
        returned as if it were tailored.
    """
    logger.info("generating_tailored_resume", bullet_count=len(verified_bullets))

    allowed = {str(b["id"]): b for b in verified_bullets if b.get("id") is not None}
    if not allowed:
        logger.warning("no_verified_bullets_available")
        return {"tailored_text": "", "used_bullet_ids": []}

    try:
        response: Any = await acompletion(
            model=settings.llm.tailoring_model,
            api_key=settings.llm.platform_groq_key or None,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(job_description, allowed)},
            ],
            temperature=0.2,
        )
        raw = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("tailoring_generation_failed", error=str(e))
        return {"tailored_text": "", "used_bullet_ids": []}

    parsed = _parse_response(raw)
    if parsed is None:
        logger.error("tailoring_response_unparseable")
        return {"tailored_text": "", "used_bullet_ids": []}

    tailored_text, used_ids = parsed

    # Enforce the containment rule in code, not just in the prompt: a model
    # that cites a bullet we never supplied has fabricated provenance, which
    # is exactly what the entailment gate exists to prevent.
    unknown = [bullet_id for bullet_id in used_ids if bullet_id not in allowed]
    if unknown:
        logger.error("tailoring_cited_unknown_bullets", unknown_ids=unknown)
        return {"tailored_text": "", "used_bullet_ids": []}

    if not used_ids or not tailored_text:
        logger.error("tailoring_returned_empty_selection")
        return {"tailored_text": "", "used_bullet_ids": []}

    logger.info("tailored_resume_generated", used_bullets=len(used_ids))
    return {"tailored_text": tailored_text, "used_bullet_ids": used_ids}


def _build_prompt(job_description: str, allowed: dict[str, dict[str, Any]]) -> str:
    """Render the JD plus the closed set of bullets the model may draw from."""
    bullets = [
        {
            "id": bullet_id,
            "text": bullet.get("bullet_text") or bullet.get("text") or "",
            "company": bullet.get("company"),
            "role": bullet.get("role"),
            "metric": bullet.get("metric"),
        }
        for bullet_id, bullet in allowed.items()
    ]
    return (
        "JOB DESCRIPTION:\n"
        f"{job_description.strip()}\n\n"
        "VERIFIED BULLETS (the only permitted source material):\n"
        f"{json.dumps(bullets, indent=2)}"
    )


def _parse_response(raw: str) -> tuple[str, list[str]] | None:
    """Extract (tailored_text, used_bullet_ids) from the model's JSON reply."""
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

    if not isinstance(payload, dict):
        return None

    tailored_text = str(payload.get("tailored_text") or "").strip()
    raw_ids = payload.get("used_bullet_ids")
    if not isinstance(raw_ids, list):
        return None

    return tailored_text, [str(bullet_id) for bullet_id in raw_ids]
