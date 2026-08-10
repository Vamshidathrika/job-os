"""Integration tests for action handlers wired to the executor."""

import pytest

from jobos.action_queue.executor import ActionExecutor
from jobos.action_queue.queue import ActionQueue
from jobos.referral.suppression import add_to_suppression
from jobos.runner.handlers import build_handlers

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


class FakeGmail:
    def __init__(self):
        self.sent = []

    async def send_email(self, to, subject, body, reply_to=None):
        self.sent.append(to)
        return {"message_id": "sent-1", "status": "sent"}


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM action_queue")
    await tenant_a_conn.execute("DELETE FROM suppression_list")
    yield
    await tenant_a_conn.execute("DELETE FROM action_queue")
    await tenant_a_conn.execute("DELETE FROM suppression_list")


async def test_referral_touch_sends_through_the_guarded_path(tenant_a_conn, tenant_a_id):
    gmail = FakeGmail()
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue(
        "referral_touch",
        {"to": "ravi@globex.example", "subject": "Hello", "body": "Hi Ravi"},
        band="A",
    )

    executor = ActionExecutor(
        queue, handlers=build_handlers(tenant_a_conn, str(tenant_a_id), gmail=gmail)
    )
    result = await executor.process_band_a()

    assert result == {"executed": 1, "failed": 0}
    assert gmail.sent == ["ravi@globex.example"]
    status = await tenant_a_conn.fetchval(
        "SELECT status FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert status == "completed"


async def test_suppressed_recipient_fails_the_action(tenant_a_conn, tenant_a_id):
    """The guard must hold even when reached through the executor."""
    await add_to_suppression(tenant_a_conn, "optedout@globex.example")
    gmail = FakeGmail()
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue(
        "referral_touch",
        {"to": "optedout@globex.example", "subject": "s", "body": "b"},
        band="A",
    )

    executor = ActionExecutor(
        queue, handlers=build_handlers(tenant_a_conn, str(tenant_a_id), gmail=gmail)
    )
    result = await executor.process_band_a()

    assert result == {"executed": 0, "failed": 1}
    assert gmail.sent == []


async def test_touch_without_a_recipient_fails_loudly(tenant_a_conn, tenant_a_id):
    gmail = FakeGmail()
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue("referral_touch", {"subject": "s", "body": "b"}, band="A")

    executor = ActionExecutor(
        queue, handlers=build_handlers(tenant_a_conn, str(tenant_a_id), gmail=gmail)
    )
    result = await executor.process_band_a()

    assert result == {"executed": 0, "failed": 1}
    assert gmail.sent == []


async def test_unimplemented_actions_refuse(tenant_a_conn, tenant_a_id):
    """Cold apply and posting must not report success they cannot deliver."""
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue("submit_application", {"job_url": "https://x.example"}, band="A")
    await queue.enqueue("publish_post", {"content": "hello"}, band="A")

    executor = ActionExecutor(
        queue, handlers=build_handlers(tenant_a_conn, str(tenant_a_id), gmail=FakeGmail())
    )
    result = await executor.process_band_a()

    assert result == {"executed": 0, "failed": 2}
