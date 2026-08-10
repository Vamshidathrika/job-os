"""Integration tests for the DB-backed action queue, executor and breaker."""

import pytest

from jobos.action_queue.executor import ActionExecutor
from jobos.action_queue.queue import ActionQueue
from jobos.calibration.circuit_breaker import CircuitBreaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean_queue(tenant_a_conn):
    """Each test starts from an empty queue for this tenant."""
    await tenant_a_conn.execute("DELETE FROM action_queue")
    yield
    await tenant_a_conn.execute("DELETE FROM action_queue")


async def test_enqueued_action_survives_a_new_queue_instance(tenant_a_conn, tenant_a_id):
    """The whole point of DB backing: state outlives the process object."""
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("send_email", {"to": "a@example.com"}, band="A")

    # A brand new instance — as a restarted worker would construct.
    reborn = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    batch = await reborn.dequeue_batch(band="A")

    assert [a["action_id"] for a in batch] == [action_id]
    assert batch[0]["payload"] == {"to": "a@example.com"}


async def test_dequeue_claims_actions_only_once(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue("send_email", {"to": "a@example.com"}, band="A")

    first = await queue.dequeue_batch(band="A")
    second = await queue.dequeue_batch(band="A")

    assert len(first) == 1
    assert second == [], "a claimed action must not be handed out twice"


async def test_invalid_band_is_rejected(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    with pytest.raises(ValueError):
        await queue.enqueue("send_email", {}, band="Z")


async def test_executor_runs_registered_handler(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("send_email", {"to": "a@example.com"}, band="A")

    seen = {}

    async def handler(payload):
        seen.update(payload)
        return {"message_id": "real-123"}

    executor = ActionExecutor(queue, handlers={"send_email": handler})
    result = await executor.process_band_a()

    assert result == {"executed": 1, "failed": 0}
    assert seen == {"to": "a@example.com"}

    row = await tenant_a_conn.fetchrow(
        "SELECT status, result FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert row["status"] == "completed"
    assert "real-123" in row["result"]


async def test_unhandled_action_type_is_recorded_as_failed(tenant_a_conn, tenant_a_id):
    """An action with no handler must fail loudly, not report success."""
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("no_such_type", {}, band="A")

    executor = ActionExecutor(queue, handlers={})
    result = await executor.process_band_a()

    assert result == {"executed": 0, "failed": 1}
    row = await tenant_a_conn.fetchrow(
        "SELECT status, error FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert row["status"] == "failed"
    assert "no_such_type" in row["error"]


async def test_handler_exception_is_persisted(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("send_email", {}, band="A")

    async def boom(payload):
        raise RuntimeError("smtp exploded")

    executor = ActionExecutor(queue, handlers={"send_email": boom})
    result = await executor.process_band_a()

    assert result == {"executed": 0, "failed": 1}
    row = await tenant_a_conn.fetchrow(
        "SELECT status, error FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert row["status"] == "failed"
    assert "smtp exploded" in row["error"]


async def test_escalation_moves_action_to_band_c(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("connect_request", {}, band="B")

    executor = ActionExecutor(queue)
    await executor.escalate_band_c(action_id)

    row = await tenant_a_conn.fetchrow(
        "SELECT band, status FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert row["band"] == "C"
    assert row["status"] == "pending"


async def test_breaker_counts_persisted_actions_not_process_state(tenant_a_conn, tenant_a_id):
    """The old in-memory breaker reset to 0 on restart, voiding the cap."""
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    for _ in range(3):
        await queue.enqueue("submit_application", {}, band="A")

    breaker = CircuitBreaker(conn=tenant_a_conn, tenant_id=str(tenant_a_id), max_daily_applies=3)
    assert await breaker.check("applies") is False

    status = await breaker.get_status()
    assert status["action_counts"]["applies"] == 3
    assert status["tripped"]["applies"] is True


async def test_breaker_allows_under_limit(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    for _ in range(2):
        await queue.enqueue("submit_application", {}, band="A")

    breaker = CircuitBreaker(conn=tenant_a_conn, tenant_id=str(tenant_a_id), max_daily_applies=5)
    assert await breaker.check("applies") is True


async def test_failed_actions_do_not_consume_daily_quota(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("submit_application", {}, band="A")
    await queue.mark_failed(action_id, error="never sent")

    breaker = CircuitBreaker(conn=tenant_a_conn, tenant_id=str(tenant_a_id), max_daily_applies=1)
    assert await breaker.check("applies") is True
