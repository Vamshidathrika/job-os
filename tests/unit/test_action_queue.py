from datetime import datetime, timedelta, timezone

import pytest

from jobos.action_queue.priority import calculate_priority
from jobos.action_queue.queue import ActionQueue

def test_calculate_priority_high_ev():
    """Test high EV score gives higher priority."""
    deadline = datetime.now(timezone.utc) + timedelta(days=5)
    
    low_ev_score = calculate_priority("apply", ev_score=0.2, deadline=deadline, tier=2)
    high_ev_score = calculate_priority("apply", ev_score=0.9, deadline=deadline, tier=2)
    
    assert high_ev_score > low_ev_score

def test_calculate_priority_deadline_proximity():
    """Test deadline proximity boosts priority."""
    now = datetime.now(timezone.utc)
    far_deadline = now + timedelta(days=15)
    close_deadline = now + timedelta(days=1)
    
    far_priority = calculate_priority("apply", ev_score=0.5, deadline=far_deadline, tier=2)
    close_priority = calculate_priority("apply", ev_score=0.5, deadline=close_deadline, tier=2)
    
    assert close_priority > far_priority

def test_calculate_priority_tier_1_boost():
    """Test Tier 1 gets priority boost."""
    deadline = datetime.now(timezone.utc) + timedelta(days=5)
    
    tier_2_score = calculate_priority("apply", ev_score=0.5, deadline=deadline, tier=2)
    tier_1_score = calculate_priority("apply", ev_score=0.5, deadline=deadline, tier=1)

    assert tier_1_score > tier_2_score


# Unit tests for ActionQueue.list_pending and mark_rejected.
#
# Scoped inside a class (rather than at module level, as the plan's snippet
# shows) so `pytestmark` and the autouse `clean` fixture below apply only to
# these DB-backed tests, not to the pre-existing calculate_priority tests
# above, which this file already contained and which need neither.
class TestActionQueuePendingAndReject:
    pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

    @pytest.fixture(autouse=True)
    async def clean(self, tenant_a_conn):
        await tenant_a_conn.execute("DELETE FROM action_queue")
        yield
        await tenant_a_conn.execute("DELETE FROM action_queue")

    async def test_list_pending_does_not_claim_rows(self, tenant_a_conn, tenant_a_id):
        queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
        action_id = await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")

        pending = await queue.list_pending()

        assert [p["action_id"] for p in pending] == [action_id]
        status = await tenant_a_conn.fetchval(
            "SELECT status FROM action_queue WHERE id = $1::uuid", action_id
        )
        assert status == "pending"  # unchanged — list_pending must not claim

    async def test_list_pending_spans_bands_and_types(self, tenant_a_conn, tenant_a_id):
        queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
        await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")
        await queue.enqueue("submit_application", {"job_url": "x"}, band="B")

        pending = await queue.list_pending()

        assert {p["action_type"] for p in pending} == {"referral_touch", "submit_application"}

    async def test_mark_rejected_sets_status(self, tenant_a_conn, tenant_a_id):
        queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
        action_id = await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")

        await queue.mark_rejected(action_id)

        status = await tenant_a_conn.fetchval(
            "SELECT status FROM action_queue WHERE id = $1::uuid", action_id
        )
        assert status == "rejected"
