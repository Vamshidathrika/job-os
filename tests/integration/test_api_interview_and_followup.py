"""Integration tests for POST /api/interview/prep and GET /api/followup/nudge.

Neither route sits behind authenticated_tenant, so there's no 401 case here.
"""

import json

import httpx
import pytest

from jobos.api import main as api_main

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


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


async def _client(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_interview_prep_returns_the_real_llm_pack_not_a_stub(db_pool, mocker):
    """Same mocking approach as tests/unit/test_interview.py."""
    mocker.patch("jobos.interview.prep.acompletion", return_value=_reply(FULL_PACK))

    async with await _client(db_pool) as client:
        response = await client.post(
            "/api/interview/prep",
            json={"title": "Backend Engineer", "company": "TechCorp", "interview_type": "phone_screen"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["likely_questions"] == ["Describe a system you scaled"]
    assert body["technical_topics"] == ["caching", "sharding"]
    assert body["answer_frameworks"] == FULL_PACK["answer_frameworks"]
    # The endpoint never passes company_context through to generate_prep_pack,
    # so company_research must come back empty regardless of what the model
    # returned for it — inventing company facts is exactly what this guards
    # against (see generate_prep_pack's docstring).
    assert body["company_research"] == {
        "key_facts": [],
        "recent_news": [],
        "culture_insights": [],
    }


async def test_interview_prep_returns_the_empty_pack_on_llm_failure(db_pool, mocker):
    mocker.patch("jobos.interview.prep.acompletion", side_effect=RuntimeError("down"))

    async with await _client(db_pool) as client:
        response = await client.post(
            "/api/interview/prep",
            json={"title": "X", "company": "Y", "interview_type": "technical"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["likely_questions"] == []
    assert body["company_research"]["key_facts"] == []


async def test_followup_nudge_reflects_days_since(db_pool):
    """generate_status_nudge reads interview['company_name']/['role_title'],
    but this endpoint passes {'company': ..., 'title': ...} — a real key
    mismatch in jobos/api/main.py, so company/role always fall back to
    generate_status_nudge's own defaults regardless of the query params.
    Asserting that real (if surprising) behavior rather than the wished-for
    'reflects the company/role query params' behavior, per this session's
    no-fabricated-expectations rule.
    """
    async with await _client(db_pool) as client:
        response = await client.get(
            "/api/followup/nudge",
            params={"company": "Postman", "role": "Senior AI Architect", "days_since": 9},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["subject"] == "Following up: Interview for the role at the company"
    assert "9 days" in body["body"]
    assert "the role" in body["body"]
    assert "the company" in body["body"]
