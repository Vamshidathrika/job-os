"""Content generator for social media platforms."""
from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion

from jobos.config import Settings, settings as default_settings

logger = structlog.get_logger(__name__)

# Platform limits that actually change what can be published.
PLATFORM_LIMITS = {
    "twitter": 280,
    "linkedin": 3000,
}

SYSTEM_PROMPT = """You write short professional social posts in the author's own voice.

Rules:
- Write from the author's stated role and experience. Never invent employers,
  metrics, projects, or credentials that are not supplied.
- No engagement bait, no "thoughts?", no hook-and-thread formatting, no emoji
  walls, no hashtag stuffing.
- Plain sentences. Specific over grand.

Return ONLY JSON: {"content": "", "hashtags": ["", ""]}"""


async def generate_engagement_post(
    topic: str,
    user_profile: dict[str, Any],
    platform: str = "linkedin",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Generate an engagement post tailored to a specific platform.

    WHAT: Uses LLM to create platform-specific content (LinkedIn/Twitter) based on a topic and user profile.
    WHY: To maintain an active online presence and establish domain expertise without manual effort.

    Raises:
        ValueError: if the model output cannot be validated. Publishing is a
            public, hard-to-retract action, so a failed generation must stop
            the pipeline rather than post filler.
    """
    settings = settings or default_settings
    logger.info("generating_engagement_post", topic=topic, platform=platform)

    limit = PLATFORM_LIMITS.get(platform.lower(), PLATFORM_LIMITS["linkedin"])
    prompt = (
        f"TOPIC: {topic}\n"
        f"PLATFORM: {platform} (hard limit {limit} characters)\n"
        f"AUTHOR: {json.dumps(user_profile)}"
    )

    try:
        response: Any = await acompletion(
            model=settings.llm.tailoring_model,
            api_key=settings.llm.platform_groq_key or None,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        raw = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("post_generation_failed", topic=topic, platform=platform, error=str(e))
        raise ValueError(f"Could not generate post for {topic!r}") from e

    payload = _parse_json_object(raw)
    if payload is None:
        raise ValueError("Model returned unparseable post content")

    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValueError("Model returned empty post content")
    if len(content) > limit:
        raise ValueError(
            f"Generated post is {len(content)} chars, over the {platform} limit of {limit}"
        )

    hashtags = payload.get("hashtags")
    normalized_tags = [
        tag if str(tag).startswith("#") else f"#{tag}"
        for tag in (hashtags if isinstance(hashtags, list) else [])
        if str(tag).strip()
    ]

    logger.info("post_generated", topic=topic, platform=platform, length=len(content))
    return {"content": content, "hashtags": normalized_tags, "platform": platform}


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
