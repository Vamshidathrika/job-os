"""Integration tests for the suppression list and the guarded send path."""

import pytest

from jobos.action_queue.queue import ActionQueue
from jobos.outbox import (
    SendingCapReachedError,
    SuppressedRecipientError,
    send_email_guarded,
)
from jobos.referral.suppression import (
    REASON_BOUNCED,
    add_to_suppression,
    check_suppression,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

SUPPRESSED = "optedout@example.com"
ALLOWED = "reachable@example.com"


class FakeGmail:
    def __init__(self):
        self.sent = []

    async def send_email(self, to, subject, body, reply_to=None):
        self.sent.append(to)
        return {"message_id": "sent-1", "status": "sent"}


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM suppression_list")
    await tenant_a_conn.execute("DELETE FROM action_queue")
    yield
    await tenant_a_conn.execute("DELETE FROM suppression_list")
    await tenant_a_conn.execute("DELETE FROM action_queue")


async def test_add_to_suppression_actually_persists(tenant_a_conn):
    """Previously every call died on a NOT NULL violation, so no opt-out stuck."""
    await add_to_suppression(tenant_a_conn, SUPPRESSED)

    assert await check_suppression(tenant_a_conn, SUPPRESSED) is True
    assert await check_suppression(tenant_a_conn, ALLOWED) is False


async def test_suppression_stores_reason_and_never_the_address(tenant_a_conn):
    await add_to_suppression(tenant_a_conn, SUPPRESSED, reason=REASON_BOUNCED)

    row = await tenant_a_conn.fetchrow("SELECT email_hash, reason FROM suppression_list")
    assert row["reason"] == REASON_BOUNCED
    assert SUPPRESSED not in row["email_hash"], "raw address must never be stored"


async def test_suppression_is_idempotent(tenant_a_conn):
    await add_to_suppression(tenant_a_conn, SUPPRESSED)
    await add_to_suppression(tenant_a_conn, SUPPRESSED)

    assert await tenant_a_conn.fetchval("SELECT count(*) FROM suppression_list") == 1


async def test_empty_reason_is_rejected(tenant_a_conn):
    with pytest.raises(ValueError):
        await add_to_suppression(tenant_a_conn, SUPPRESSED, reason="")


async def test_suppression_applies_across_tenants(tenant_a_conn, tenant_b_conn):
    """The list is global: an opt-out must bind every tenant, not just one."""
    await add_to_suppression(tenant_a_conn, SUPPRESSED)

    assert await check_suppression(tenant_b_conn, SUPPRESSED) is True


async def test_guarded_send_delivers_to_allowed_recipient(tenant_a_conn, tenant_a_id):
    gmail = FakeGmail()

    result = await send_email_guarded(
        tenant_a_conn, gmail, str(tenant_a_id), to=ALLOWED, subject="s", body="b"
    )

    assert gmail.sent == [ALLOWED]
    assert result["message_id"] == "sent-1"


async def test_guarded_send_refuses_suppressed_recipient(tenant_a_conn, tenant_a_id):
    """The whole point: a suppressed address must never reach the provider."""
    await add_to_suppression(tenant_a_conn, SUPPRESSED)
    gmail = FakeGmail()

    with pytest.raises(SuppressedRecipientError):
        await send_email_guarded(
            tenant_a_conn, gmail, str(tenant_a_id), to=SUPPRESSED, subject="s", body="b"
        )

    assert gmail.sent == [], "no send may occur for a suppressed recipient"


async def test_guarded_send_refuses_once_daily_cap_is_spent(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    for _ in range(10):  # default max_daily_emails
        await queue.enqueue("send_email", {}, band="A")

    gmail = FakeGmail()
    with pytest.raises(SendingCapReachedError):
        await send_email_guarded(
            tenant_a_conn, gmail, str(tenant_a_id), to=ALLOWED, subject="s", body="b"
        )

    assert gmail.sent == []
