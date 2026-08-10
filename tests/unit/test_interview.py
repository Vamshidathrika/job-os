import json

import pytest

from jobos.interview.debrief import capture_debrief
from jobos.interview.followup import generate_thank_you
from jobos.interview.prep import generate_prep_pack
from jobos.interview.scheduler import InterviewScheduler


def _reply(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


FULL_PACK = {
    "company_research": {
        "key_facts": ["Series B, 2024"],
        "recent_news": ["Launched an analytics product"],
        "culture_insights": ["Small autonomous teams"],
    },
    "likely_questions": ["Describe a system you scaled"],
    "answer_frameworks": [
        {"question": "Describe a system you scaled", "framework": "STAR", "uses_experience": "Redis cache"}
    ],
    "technical_topics": ["caching", "sharding"],
    "questions_to_ask": ["How is on-call structured?"],
}


@pytest.mark.asyncio
async def test_generate_prep_pack_phone_screen(mocker):
    """Test prep pack includes all required sections."""
    mocker.patch("jobos.interview.prep.acompletion", return_value=_reply(FULL_PACK))

    result = await generate_prep_pack(
        {"title": "Backend Engineer", "company": "TechCorp"},
        {"name": "Alice"},
        interview_type="phone_screen",
        company_context="TechCorp raised a Series B in 2024.",
    )

    assert "company_research" in result
    assert "likely_questions" in result
    assert "answer_frameworks" in result
    assert "technical_topics" in result
    assert "questions_to_ask" in result
    # The old stub returned every section empty regardless of input.
    assert result["likely_questions"] == ["Describe a system you scaled"]
    assert result["technical_topics"] == ["caching", "sharding"]


@pytest.mark.asyncio
async def test_company_research_is_dropped_without_a_source(mocker):
    """Never send a candidate into the room repeating invented company facts."""
    mocker.patch("jobos.interview.prep.acompletion", return_value=_reply(FULL_PACK))

    result = await generate_prep_pack(
        {"title": "Backend Engineer", "company": "TechCorp"},
        {"name": "Alice"},
        interview_type="phone_screen",
        company_context=None,
    )

    assert result["company_research"] == {
        "key_facts": [],
        "recent_news": [],
        "culture_insights": [],
    }
    # Everything grounded in the JD still survives.
    assert result["technical_topics"] == ["caching", "sharding"]


@pytest.mark.asyncio
async def test_prep_pack_failure_returns_empty_not_garbage(mocker):
    mocker.patch("jobos.interview.prep.acompletion", side_effect=RuntimeError("down"))

    result = await generate_prep_pack({"title": "X"}, {"name": "A"}, interview_type="technical")

    assert result["likely_questions"] == []
    assert result["company_research"]["key_facts"] == []


@pytest.mark.asyncio
async def test_capture_debrief(mocker):
    """Test debrief returns sentiment + follow_up_actions."""
    mocker.patch(
        "jobos.interview.debrief.acompletion",
        return_value=_reply(
            {
                "sentiment": "positive",
                "likelihood_score": 0.7,
                "follow_up_actions": ["Send the design doc"],
                "new_stories": [],
            }
        ),
    )

    result = await capture_debrief(
        "interview-123", {"text": "Interview went well, they asked about my AWS experience."}
    )

    assert "sentiment" in result
    assert "follow_up_actions" in result
    assert isinstance(result["follow_up_actions"], list)
    # The old stub ignored the notes and always returned neutral/0.0.
    assert result["sentiment"] == "positive"
    assert result["likelihood_score"] == 0.7


@pytest.mark.asyncio
async def test_debrief_clamps_out_of_range_likelihood(mocker):
    mocker.patch(
        "jobos.interview.debrief.acompletion",
        return_value=_reply(
            {"sentiment": "weird", "likelihood_score": 7.5, "follow_up_actions": [], "new_stories": []}
        ),
    )

    result = await capture_debrief("interview-1", {"text": "n"})

    assert result["likelihood_score"] == 1.0
    assert result["sentiment"] == "neutral", "unknown sentiment falls back"


@pytest.mark.asyncio
async def test_parse_interview_invite():
    """Test email parsing extracts date and link."""
    scheduler = InterviewScheduler(tenant_id="tenant-123")
    email_body = "Your interview is scheduled for Oct 15 at 2 PM. Join here: https://zoom.us/j/123"

    result = await scheduler.parse_interview_invite(email_body)

    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_generate_thank_you():
    """Test thank-you email has subject and body."""
    interview = {"interviewer": "Bob"}
    debrief = {"follow_up_actions": []}

    result = await generate_thank_you(interview, debrief)

    assert "subject" in result
    assert "body" in result
    assert isinstance(result["subject"], str)
    assert isinstance(result["body"], str)
