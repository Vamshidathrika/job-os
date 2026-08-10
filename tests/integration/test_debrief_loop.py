"""Integration tests for the compounding debrief loop.

The README's claim is that a post-interview debrief "appends new STAR stories
back to the candidate's Career Graph". These tests hold that claim to the
database.
"""

import json

import pytest

from jobos.interview.debrief import capture_debrief

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM agent_decisions")
    yield
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM agent_decisions")


def _reply(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


DEBRIEF_WITH_STORY = {
    "sentiment": "positive",
    "likelihood_score": 0.8,
    "follow_up_actions": ["Send the architecture diagram"],
    "new_stories": [
        {
            "bullet_text": "Cut nightly batch runtime from 6h to 40m by repartitioning the job",
            "company": "Acme",
            "role": "Backend Engineer",
            "metric": "6h -> 40m",
        }
    ],
}


async def test_new_stories_land_in_the_career_graph(tenant_a_conn, tenant_a_id, mocker):
    mocker.patch(
        "jobos.interview.debrief.acompletion", return_value=_reply(DEBRIEF_WITH_STORY)
    )

    await capture_debrief(
        "interview-1",
        {"text": "Told them about the batch job rewrite."},
        conn=tenant_a_conn,
        user_id=str(tenant_a_id),
    )

    row = await tenant_a_conn.fetchrow(
        "SELECT bullet_text, company, metric, verification_status FROM cg_bullets"
    )
    assert row is not None, "the loop must actually append to the Career Graph"
    assert "repartitioning" in row["bullet_text"]
    assert row["company"] == "Acme"
    assert row["verification_status"] == "unverified", (
        "recalled stories must enter unverified so the tailorer cannot use them "
        "until they pass the verification ladder"
    )


async def test_debrief_itself_is_recorded(tenant_a_conn, tenant_a_id, mocker):
    mocker.patch(
        "jobos.interview.debrief.acompletion", return_value=_reply(DEBRIEF_WITH_STORY)
    )

    await capture_debrief(
        "interview-1", {"text": "n"}, conn=tenant_a_conn, user_id=str(tenant_a_id)
    )

    row = await tenant_a_conn.fetchrow(
        "SELECT outputs FROM agent_decisions WHERE module = 'interview'"
    )
    assert row is not None
    assert json.loads(row["outputs"])["sentiment"] == "positive"


async def test_debrief_without_stories_adds_no_bullets(tenant_a_conn, tenant_a_id, mocker):
    mocker.patch(
        "jobos.interview.debrief.acompletion",
        return_value=_reply(
            {
                "sentiment": "negative",
                "likelihood_score": 0.1,
                "follow_up_actions": [],
                "new_stories": [],
            }
        ),
    )

    await capture_debrief(
        "interview-2", {"text": "Did not go well."}, conn=tenant_a_conn, user_id=str(tenant_a_id)
    )

    assert await tenant_a_conn.fetchval("SELECT count(*) FROM cg_bullets") == 0


async def test_stories_are_tenant_isolated(tenant_a_conn, tenant_b_conn, tenant_a_id, mocker):
    mocker.patch(
        "jobos.interview.debrief.acompletion", return_value=_reply(DEBRIEF_WITH_STORY)
    )

    await capture_debrief(
        "interview-1", {"text": "n"}, conn=tenant_a_conn, user_id=str(tenant_a_id)
    )

    assert await tenant_b_conn.fetchval("SELECT count(*) FROM cg_bullets") == 0


async def test_llm_failure_persists_nothing(tenant_a_conn, tenant_a_id, mocker):
    mocker.patch("jobos.interview.debrief.acompletion", side_effect=RuntimeError("down"))

    result = await capture_debrief(
        "interview-3", {"text": "n"}, conn=tenant_a_conn, user_id=str(tenant_a_id)
    )

    assert result["follow_up_actions"] == []
    assert await tenant_a_conn.fetchval("SELECT count(*) FROM cg_bullets") == 0
    assert await tenant_a_conn.fetchval("SELECT count(*) FROM agent_decisions") == 0
