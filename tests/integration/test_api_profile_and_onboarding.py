"""Integration tests for POST /api/profile/analyze, GET /api/onboarding/wizard,
POST /api/onboarding/step, and GET /api/career-graph/summary.
"""

import json
import uuid

import httpx
import pytest

from jobos.api import main as api_main
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _llm_json(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people WHERE source = 'linkedin_connection'")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    api_main.app.state.pool = db_pool
    yield
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people WHERE source = 'linkedin_connection'")
    await tenant_a_conn.execute("DELETE FROM api_tokens")


async def _client(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _client_and_token(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")
    return await _client(db_pool), token


async def test_analyze_profile_returns_the_real_llm_score_not_a_stub(db_pool, mocker):
    """Same mocking approach as tests/unit/test_profile.py."""
    mocker.patch(
        "jobos.profile.optimizer.acompletion",
        return_value=_llm_json(
            {
                "score": 62,
                "suggestions": [{"section": "summary", "suggestion": "Add measurable outcomes."}],
                "headline_options": ["Backend Engineer | Python, AWS"],
            }
        ),
    )

    async with await _client(db_pool) as client:
        response = await client.post(
            "/api/profile/analyze",
            json={
                "headline": "Software Engineer",
                "summary": "Building scalable systems.",
                "experience": [],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["score"] == 62
    assert body["suggestions"] == [{"section": "summary", "suggestion": "Add measurable outcomes."}]
    assert body["headline_options"] == ["Backend Engineer | Python, AWS"]


async def test_analyze_profile_falls_back_to_structural_score_on_llm_failure(db_pool, mocker):
    mocker.patch("jobos.profile.optimizer.acompletion", side_effect=RuntimeError("down"))

    async with await _client(db_pool) as client:
        response = await client.post(
            "/api/profile/analyze",
            json={"headline": "", "summary": "", "experience": []},
        )

    assert response.status_code == 200
    body = response.json()
    # Deterministic structural fallback: every completeness check fails, so
    # the real computed score is 0, never a fabricated placeholder.
    assert body["score"] == 0.0
    sections = {s["section"] for s in body["suggestions"]}
    assert sections == {"headline", "summary", "experience", "skills"}


async def test_wizard_status_starts_at_zero_percent(db_pool, tenant_a_id):
    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.get(
            "/api/onboarding/wizard", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["completed_steps"] == []
    assert body["percent_complete"] == 0.0
    assert set(body["pending_steps"]) == {
        "resume_upload",
        "target_roles",
        "target_companies",
        "location_preferences",
        "salary_expectations",
        "integration_setup",
    }


async def test_submit_step_reflects_that_step_as_completed(db_pool, tenant_a_id):
    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.post(
            "/api/onboarding/step",
            json={"step_name": "target_roles", "data": {"roles": ["Backend Engineer"]}},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["completed_steps"] == ["target_roles"]
    assert "target_roles" not in body["pending_steps"]
    # 1 of 6 steps, computed the same way OnboardingWizard.get_progress does.
    assert body["percent_complete"] == pytest.approx(100 / 6)


async def test_submit_step_with_an_unknown_step_name_is_rejected(db_pool, tenant_a_id):
    """The wizard's own submit_step raises ValueError for a step outside its
    fixed list; main.py has no try/except around this call, so it propagates
    rather than silently accepting a made-up step name."""
    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        with pytest.raises(ValueError, match="Invalid step"):
            await client.post(
                "/api/onboarding/step",
                json={"step_name": "not_a_real_step", "data": {}},
                headers={"Authorization": f"Bearer {token}"},
            )


async def test_career_graph_summary_counts_real_rows(tenant_a_conn, tenant_a_id, db_pool):
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Acme', 'Engineer', 'Built a thing', 'verified')",
        tenant_a_id,
    )
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Acme', 'Engineer', 'Claimed a thing', 'unverified')",
        tenant_a_id,
    )
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, source) "
        "VALUES (gen_random_uuid(), $1, 'Ravi Kumar', 'globex.example', 'linkedin_connection')",
        tenant_a_id,
    )

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.get(
            "/api/career-graph/summary", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["bullets_total"] == 2
    assert body["bullets_verified"] == 1
    assert body["linkedin_connections"] == 1


async def test_career_graph_summary_without_a_token_is_rejected(db_pool):
    async with await _client(db_pool) as client:
        response = await client.get("/api/career-graph/summary")
    assert response.status_code == 401
