"""Comment generator for social media posts."""
from __future__ import annotations

from typing import Any
import structlog
from litellm import acompletion

from jobos.config import Settings, settings as default_settings
from jobos.utils.text_matching import compute_fuzzy_similarity

logger = structlog.get_logger(__name__)

MAX_COMMENT_LENGTH = 400

# Two comments this similar in structure read as automation to both the
# platform's spam filters and to any human scrolling the feed.
MAX_STRUCTURAL_SIMILARITY = 0.40

SYSTEM_PROMPT = """You write one short comment replying to a specific social post.

Rules:
- Respond to something concrete in the post. Never generic praise
  ("great post", "couldn't agree more", "fascinating perspective").
- Draw only on the author's stated expertise. Never claim to have used the
  product, worked at the company, or seen results you were not told about.
- One or two sentences. No emoji, no hashtags, no pitch, no self-promotion.

Return ONLY the comment text."""


async def generate_smart_comment(
    post_content: str,
    user_expertise: list[str],
    target_company: str,
    recent_comments: list[str] | None = None,
    settings: Settings | None = None,
) -> str:
    """
    Generate a smart, non-generic comment for a target company's post.

    WHAT: Analyzes post content and user expertise to craft a thoughtful, value-add comment.
    WHY: To engage with target companies authentically and avoid spam filters by ensuring structural uniqueness.

    Raises:
        ValueError: if generation fails or the result is too close to a recent
            comment. Commenting is public and rate-limited, so a near-duplicate
            must be refused rather than posted.
    """
    settings = settings or default_settings
    logger.info("generating_smart_comment", target_company=target_company)

    prompt = (
        f"POST BY {target_company}:\n{post_content.strip()}\n\n"
        f"COMMENTER'S EXPERTISE: {', '.join(user_expertise) or 'unspecified'}"
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
        comment = str(response["choices"][0]["message"]["content"]).strip()
    except Exception as e:
        logger.error("comment_generation_failed", target_company=target_company, error=str(e))
        raise ValueError(f"Could not generate a comment for {target_company!r}") from e

    comment = comment.strip('"').strip()
    if not comment:
        raise ValueError("Model returned an empty comment")
    if len(comment) > MAX_COMMENT_LENGTH:
        raise ValueError(f"Comment is {len(comment)} chars, over the {MAX_COMMENT_LENGTH} limit")

    for previous in recent_comments or []:
        similarity = compute_fuzzy_similarity(comment, previous)
        if similarity > MAX_STRUCTURAL_SIMILARITY:
            raise ValueError(
                f"Comment is {similarity:.0%} similar to a recent one; refusing to post a near-duplicate"
            )

    logger.info("comment_generated", target_company=target_company, length=len(comment))
    return comment
