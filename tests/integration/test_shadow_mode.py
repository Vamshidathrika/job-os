"""Integration tests for shadow mode, the new-tenant safety guardrail."""

import json

import pytest

from jobos.action_queue.queue import ActionQueue
from jobos.onboarding.shadow_mode import ShadowMode

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def reset_state(tenant_a_conn, tenant_a_id):
    await tenant_a_conn.execute("DELETE FROM action_queue")
    await tenant_a_conn.execute("DELETE FROM agent_decisions")
    await tenant_a_conn.execute(
        "UPDATE tenants SET autonomy_mode = 'shadow' WHERE id = $1", tenant_a_id
    )
    yield
    await tenant_a_conn.execute("DELETE FROM action_queue")
    await tenant_a_conn.execute("DELETE FROM agent_decisions")


async def test_new_tenant_starts_in_shadow_mode(tenant_a_conn, tenant_a_id):
    shadow = ShadowMode(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    assert await shadow.is_enabled() is True


async def test_mode_change_persists_across_instances(tenant_a_conn, tenant_a_id):
    """The old flag lived on the instance, so it reset on every request."""
    await ShadowMode(conn=tenant_a_conn, tenant_id=str(tenant_a_id)).disable()

    reborn = ShadowMode(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    assert await reborn.is_enabled() is False

    await reborn.enable()
    assert await ShadowMode(conn=tenant_a_conn, tenant_id=str(tenant_a_id)).is_enabled() is True


async def test_unknown_tenant_fails_safe_to_shadow(tenant_a_conn):
    shadow = ShadowMode(conn=tenant_a_conn, tenant_id="99999999-9999-9999-9999-999999999999")
    assert await shadow.is_enabled() is True


async def test_proposed_actions_are_real_queue_rows(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue("send_email", {"to": "a@example.com"}, band="B")
    await queue.enqueue("submit_application", {}, band="A")  # auto band, not for review

    shadow = ShadowMode(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    proposed = await shadow.get_proposed_actions()

    assert [p["action_type"] for p in proposed] == ["send_email"]
    assert proposed[0]["payload"] == {"to": "a@example.com"}


async def test_approving_moves_action_into_the_auto_band(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("send_email", {}, band="B")

    shadow = ShadowMode(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await shadow.approve_action(action_id)

    row = await tenant_a_conn.fetchrow(
        "SELECT band, status FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert row["band"] == "A"
    assert row["status"] == "pending"


async def test_approving_an_unknown_action_raises(tenant_a_conn, tenant_a_id):
    shadow = ShadowMode(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    with pytest.raises(LookupError):
        await shadow.approve_action("99999999-9999-9999-9999-999999999999")


async def test_rejection_is_persisted_for_calibration(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("send_email", {}, band="B")

    shadow = ShadowMode(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await shadow.reject_action(action_id, reason="tone is off")

    row = await tenant_a_conn.fetchrow(
        "SELECT status, error FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert row["status"] == "rejected"
    assert row["error"] == "tone is off"

    decision = await tenant_a_conn.fetchrow(
        "SELECT outputs FROM agent_decisions WHERE module = 'shadow_mode'"
    )
    assert decision is not None
    assert json.loads(decision["outputs"])["reason"] == "tone is off"


async def test_rejected_actions_are_not_re_proposed(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("send_email", {}, band="B")
    shadow = ShadowMode(conn=tenant_a_conn, tenant_id=str(tenant_a_id))

    await shadow.reject_action(action_id, reason="no")

    assert await shadow.get_proposed_actions() == []
