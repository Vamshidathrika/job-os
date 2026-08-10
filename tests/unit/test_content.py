import json

import pytest

from jobos.content.comment_engine import generate_smart_comment
from jobos.content.generator import generate_engagement_post


def _llm_json(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def _llm_text(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


async def test_generate_engagement_post_linkedin(mocker):
    """Test LinkedIn post generation returns content + hashtags."""
    mocker.patch(
        "jobos.content.generator.acompletion",
        return_value=_llm_json(
            {
                "content": "Cutting p99 latency meant fixing our cache keys, not adding servers.",
                "hashtags": ["backend", "#latency"],
            }
        ),
    )

    result = await generate_engagement_post(
        "AI in Recruitment", {"title": "Software Engineer"}, platform="linkedin"
    )

    assert isinstance(result["content"], str) and result["content"]
    assert result["hashtags"] == ["#backend", "#latency"], "tags must be normalized"


async def test_post_over_platform_limit_is_rejected(mocker):
    """A 400-char tweet cannot be published — refuse instead of truncating."""
    mocker.patch(
        "jobos.content.generator.acompletion",
        return_value=_llm_json({"content": "x" * 400, "hashtags": []}),
    )

    with pytest.raises(ValueError, match="over the twitter limit"):
        await generate_engagement_post("topic", {"title": "SWE"}, platform="twitter")


async def test_post_generation_failure_raises(mocker):
    """Publishing is public and hard to retract — never post filler."""
    mocker.patch(
        "jobos.content.generator.acompletion", side_effect=RuntimeError("provider down")
    )

    with pytest.raises(ValueError):
        await generate_engagement_post("topic", {"title": "SWE"})


async def test_generate_smart_comment(mocker):
    """Test comment is non-empty and relevant."""
    mocker.patch(
        "jobos.content.comment_engine.acompletion",
        return_value=_llm_text("Curious how the ATS handles duplicate candidate records at scale."),
    )

    comment = await generate_smart_comment(
        "We are releasing our new ATS platform today.",
        ["Python", "System Design"],
        "TechCorp",
    )

    assert isinstance(comment, str) and comment
    # The old template pasted the company name and expertise verbatim.
    assert "fascinating perspective" not in comment.lower()


async def test_near_duplicate_comment_is_refused(mocker):
    """Structurally identical comments read as automation and get filtered."""
    text = "Curious how the ATS handles duplicate candidate records at scale."
    mocker.patch("jobos.content.comment_engine.acompletion", return_value=_llm_text(text))

    with pytest.raises(ValueError, match="similar"):
        await generate_smart_comment(
            "New ATS platform", ["Python"], "TechCorp", recent_comments=[text]
        )


async def test_comment_generation_failure_raises(mocker):
    mocker.patch(
        "jobos.content.comment_engine.acompletion", side_effect=RuntimeError("down")
    )

    with pytest.raises(ValueError):
        await generate_smart_comment("post", ["Python"], "TechCorp")
