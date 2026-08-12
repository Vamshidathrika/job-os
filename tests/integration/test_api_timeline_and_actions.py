"""Integration tests for GET /api/timeline and GET /api/actions.

tests/integration/test_api_execute_action.py already covers
GET /api/actions?status=pending (test_list_pending_actions_across_bands), so
this file covers the other query path instead: the default band= dequeue
(dequeue_batch), which claims rows rather than just listing them.
"""

import httpx
import pytest

from jobos.action_queue.queue import ActionQueue
from jobos.api import main as api_main
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


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
    return httpx.AsyncClient(transport=transport, base_url="http://test"), token


async def test_timeline_shows_a_real_completed_action(tenant_a_conn, tenant_a_id, db_pool):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue(
        "referral_touch", {"to": "a@b.com", "company": "Acme Timeline", "role": "Backend Engineer"}, band="A"
    )
    await queue.mark_complete(action_id=action_id, result={"sent": True})

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.get(
            "/api/timeline?days=30", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    entries = [e for e in body if e["id"] == action_id]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["type"] == "referral_touch"
    assert entry["details"]["company"] == "Acme Timeline"
    assert entry["details"]["role"] == "Backend Engineer"
    assert entry["timestamp"] is not None


async def test_timeline_omits_actions_still_pending(tenant_a_conn, tenant_a_id, db_pool):
    """Only completed work belongs on a timeline of what actually happened."""
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.get(
            "/api/timeline?days=30", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert action_id not in {e["id"] for e in response.json()}


async def test_actions_dequeue_claims_pending_rows_for_the_requested_band(
    tenant_a_conn, tenant_a_id, db_pool
):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    a_id = await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")
    b_id = await queue.enqueue("submit_application", {}, band="B")

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.get(
            "/api/actions?band=A", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert [a["action_id"] for a in body] == [a_id]
    assert body[0]["action_type"] == "referral_touch"
    # dequeue_batch's UPDATE actually claims the row — status flips to
    # 'processing', unlike list_pending which never touches status.
    assert body[0]["status"] == "processing"

    row = await tenant_a_conn.fetchrow(
        "SELECT status FROM action_queue WHERE id = $1::uuid", a_id
    )
    assert row["status"] == "processing"
    # The band=B action must not have been claimed by a band=A request.
    other_row = await tenant_a_conn.fetchrow(
        "SELECT status FROM action_queue WHERE id = $1::uuid", b_id
    )
    assert other_row["status"] == "pending"


async def test_timeline_without_a_token_is_rejected(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/timeline")
    assert response.status_code == 401
