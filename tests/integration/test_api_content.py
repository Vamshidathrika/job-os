"""Integration tests for POST /api/content/generate and GET /api/content/comment.

Both wrap functions that call litellm.acompletion (a real Groq call). Reusing
the exact mocking approach already established in tests/unit/test_content.py:
mocker.patch("jobos.content.generator.acompletion", ...) /
mocker.patch("jobos.content.comment_engine.acompletion", ...) — so these
tests need no real network access or API key.

Neither route sits behind authenticated_tenant, so there's no 401 case here.
"""

import json

import httpx
import pytest

from jobos.api import main as api_main

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _llm_json(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def _llm_text(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


async def _client(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_generate_post_returns_the_real_llm_result_not_a_stub(db_pool, mocker):
    mocker.patch(
        "jobos.content.generator.acompletion",
        return_value=_llm_json(
            {
                "content": "Cutting p99 latency meant fixing our cache keys, not adding servers.",
                "hashtags": ["backend", "#latency"],
            }
        ),
    )

    async with await _client(db_pool) as client:
        response = await client.post(
            "/api/content/generate", json={"topic": "AI in Recruitment", "platform": "linkedin"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "Cutting p99 latency meant fixing our cache keys, not adding servers."
    # Confirms real normalization ran (bare tag gets '#' prefixed) rather than
    # the mock's raw payload being echoed straight through.
    assert body["hashtags"] == ["#backend", "#latency"]
    assert body["platform"] == "linkedin"


async def test_generate_post_over_platform_limit_propagates_as_a_failure(db_pool, mocker):
    """Publishing is public and hard to retract — the endpoint must not
    swallow this into a 200 with filler content."""
    mocker.patch(
        "jobos.content.generator.acompletion",
        return_value=_llm_json({"content": "x" * 400, "hashtags": []}),
    )

    async with await _client(db_pool) as client:
        with pytest.raises(ValueError, match="over the twitter limit"):
            await client.post(
                "/api/content/generate", json={"topic": "topic", "platform": "twitter"}
            )


async def test_comment_returns_the_real_llm_result_not_a_template(db_pool, mocker):
    mocker.patch(
        "jobos.content.comment_engine.acompletion",
        return_value=_llm_text(
            "Curious how the ATS handles duplicate candidate records at scale."
        ),
    )

    async with await _client(db_pool) as client:
        response = await client.get(
            "/api/content/comment",
            params={"post_text": "We are releasing our new ATS platform today.", "company": "TechCorp"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["comment"] == "Curious how the ATS handles duplicate candidate records at scale."
    # The old template pasted the company name/expertise verbatim.
    assert "fascinating perspective" not in body["comment"].lower()
