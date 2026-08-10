"""Post-interview debrief capture."""

from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion

from jobos.config import Settings, settings as default_settings

logger = structlog.get_logger(__name__)

VALID_SENTIMENTS = ("positive", "neutral", "negative")

SYSTEM_PROMPT = """You structure a candidate's notes from an interview they just had.

Rules:
- Use ONLY what the notes say. Never invent questions that were asked,
  outcomes, or interviewer reactions.
- sentiment: how the interview appears to have gone, from the notes alone.
- likelihood_score: 0.0-1.0, the candidate's apparent chance of advancing.
  Use 0.5 when the notes give no signal either way.
- follow_up_actions: concrete things the candidate said they must do next.
- new_stories: achievements the candidate described that read like reusable
  STAR examples. Copy the substance from the notes; do not embellish. Return
  an empty list if the notes contain none.

Return ONLY JSON:
{"sentiment": "positive|neutral|negative",
 "likelihood_score": 0.0,
 "follow_up_actions": [""],
 "new_stories": [{"bullet_text": "", "company": "", "role": "", "metric": ""}]}"""


async def capture_debrief(
    interview_id: str,
    notes: dict[str, Any],
    conn: Any = None,
    user_id: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Capture post-interview debrief details.

    Args:
        interview_id: The ID of the interview.
        notes: User's notes and thoughts from the interview.
        conn: Optional tenant-scoped connection. When supplied along with
            user_id, the debrief is persisted and any new STAR stories are
            appended to the Career Graph — this is what makes the loop
            compounding rather than write-only.
        user_id: The owning user, required to persist.
        settings: Application settings; defaults to the global singleton.

    Returns:
        dict[str, Any]: Structured debrief containing sentiment, follow_up_actions, and likelihood_score.
    """
    settings = settings or default_settings
    logger.info("capturing_debrief", interview_id=interview_id)

    debrief = await _structure_notes(notes, settings)
    if debrief is None:
        logger.error("debrief_structuring_failed", interview_id=interview_id)
        # Neutral placeholder values are returned only on failure, and the
        # caller can tell them apart by the empty follow_up_actions.
        return {"sentiment": "neutral", "follow_up_actions": [], "likelihood_score": 0.0}

    if conn is not None and user_id:
        await _persist(conn, user_id, interview_id, notes, debrief)

    logger.info(
        "debrief_captured",
        interview_id=interview_id,
        sentiment=debrief["sentiment"],
        new_stories=len(debrief["new_stories"]),
    )
    return debrief


async def _structure_notes(notes: dict[str, Any], settings: Settings) -> dict[str, Any] | None:
    """Turn free-form notes into the debrief schema, or None on failure."""
    try:
        response: Any = await acompletion(
            model=settings.llm.tailoring_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(notes, indent=2, default=str)},
            ],
            temperature=0.0,
        )
        raw = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("debrief_llm_failed", error=str(e))
        return None

    payload = _parse_json_object(raw)
    if payload is None:
        return None

    sentiment = str(payload.get("sentiment", "")).strip().lower()
    if sentiment not in VALID_SENTIMENTS:
        sentiment = "neutral"

    try:
        likelihood = float(payload.get("likelihood_score"))
    except (TypeError, ValueError):
        likelihood = 0.5
    likelihood = max(0.0, min(1.0, likelihood))

    actions = payload.get("follow_up_actions")
    stories = payload.get("new_stories")

    return {
        "sentiment": sentiment,
        "likelihood_score": likelihood,
        "follow_up_actions": [str(a) for a in actions if str(a).strip()]
        if isinstance(actions, list)
        else [],
        "new_stories": [s for s in stories if isinstance(s, dict) and s.get("bullet_text")]
        if isinstance(stories, list)
        else [],
    }


async def _persist(
    conn: Any,
    user_id: str,
    interview_id: str,
    notes: dict[str, Any],
    debrief: dict[str, Any],
) -> None:
    """Record the debrief and append any new stories to the Career Graph."""
    await conn.execute(
        """
        INSERT INTO agent_decisions (id, user_id, module, action, inputs, outputs)
        VALUES (gen_random_uuid(), $1::uuid, 'interview', 'capture_debrief', $2::jsonb, $3::jsonb)
        """,
        user_id,
        json.dumps({"interview_id": interview_id, "notes": notes}, default=str),
        json.dumps(debrief, default=str),
    )

    for story in debrief["new_stories"]:
        # Stories enter unverified: they came from the candidate's recollection,
        # so they must pass the same verification ladder as any other bullet
        # before the tailorer is allowed to use them.
        await conn.execute(
            """
            INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, metric, verification_status)
            VALUES (gen_random_uuid(), $1::uuid, $2, $3, $4, $5, 'unverified')
            """,
            user_id,
            story.get("company"),
            story.get("role"),
            str(story["bullet_text"]),
            story.get("metric"),
        )


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
