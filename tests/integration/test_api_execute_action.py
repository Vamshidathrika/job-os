"""Integration test for POST /api/actions/{id}/execute.

First test to exercise jobos/api/main.py directly — a gap flagged in
HANDOFF.md. Scoped to the bug this session found and fixed: the endpoint
used to mark every action 'completed' with a fixed {"executed": True}
result regardless of action_type, without running anything — a human
clicking "approve" in the dashboard had no real effect.
"""

from pathlib import Path

import httpx
import pytest

from jobos.api import main as api_main
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

FIXTURE_URL = "file://" + str(
    Path(__file__).resolve().parents[2] / "jobos" / "cold_apply" / "fixtures" / "greenhouse_form.html"
)


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM action_queue")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    api_main.app.state.pool = db_pool
    yield
    await tenant_a_conn.execute("DELETE FROM action_queue")
    await tenant_a_conn.execute("DELETE FROM api_tokens")


async def _client_and_token(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")
    transport = httpx.ASGITransport(app=api_main.app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return client, token


async def test_execute_runs_the_real_handler_not_a_fake_success(
    tenant_a_conn, tenant_a_id, db_pool
):
    from jobos.action_queue.queue import ActionQueue

    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue(
        "submit_application", {"job_url": FIXTURE_URL, "answers": {"first name": "Asha"}}, band="B"
    )

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.post(
            f"/api/actions/{action_id}/execute",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    # The old behavior returned exactly {"executed": True} with nothing real
    # in it. The real handler's result must be substantively different.
    assert body["result"] != {"executed": True}
    assert body["result"]["status"] == "prepared_for_review"
    Path(body["result"]["screenshot_path"]).unlink(missing_ok=True)

    row = await tenant_a_conn.fetchrow(
        "SELECT status FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert row["status"] == "completed"


async def test_execute_persists_a_real_failure_not_a_fake_completion(
    tenant_a_conn, tenant_a_id, db_pool
):
    from jobos.action_queue.queue import ActionQueue

    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("referral_touch", {}, band="B")  # no 'to' -> handler raises

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.post(
            f"/api/actions/{action_id}/execute",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 502
    row = await tenant_a_conn.fetchrow(
        "SELECT status, error FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert row["status"] == "failed"
    assert row["error"]


async def test_execute_without_a_token_is_rejected(tenant_a_conn, tenant_a_id, db_pool):
    from jobos.action_queue.queue import ActionQueue

    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("referral_touch", {}, band="B")

    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/actions/{action_id}/execute")

    assert response.status_code == 401
