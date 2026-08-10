"""Circuit breaker for runaway automation."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Action types counted against each daily cap.
ACTION_TYPES_BY_LIMIT = {
    "applies": ("submit_application", "cold_apply"),
    "emails": ("send_email", "referral_touch"),
}


class CircuitBreaker:
    """Prevents runaway automation by enforcing daily caps.

    Counts are read from the persisted action_queue rather than kept in
    memory: an in-process counter resets to zero on every restart or extra
    worker, which silently voids the cap it is supposed to enforce.
    """

    def __init__(
        self,
        conn: Any,
        tenant_id: str,
        max_daily_applies: int = 20,
        max_daily_emails: int = 10,
    ) -> None:
        """Initialize the CircuitBreaker.

        Args:
            conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn).
            tenant_id: The ID of the tenant.
            max_daily_applies: Maximum number of applications allowed per day.
            max_daily_emails: Maximum number of emails allowed per day.
        """
        self.conn = conn
        self.tenant_id = tenant_id
        self.limits = {"applies": max_daily_applies, "emails": max_daily_emails}
        self._logger = logger.bind(tenant_id=tenant_id)

    async def _count_today(self, action_kind: str) -> int:
        """Count today's non-failed actions for a limit category."""
        action_types = ACTION_TYPES_BY_LIMIT.get(action_kind)
        if not action_types:
            raise ValueError(f"Unknown action kind: {action_kind}")

        return await self.conn.fetchval(
            """
            SELECT count(*) FROM action_queue
            WHERE action_type = ANY($1::text[])
              AND status <> 'failed'
              AND created_at > now() - make_interval(days => 1)
            """,
            list(action_types),
        )

    async def check(self, action_kind: str) -> bool:
        """Check if a specific action is allowed.

        Args:
            action_kind: The limit category ('applies' or 'emails').

        Returns:
            True if the action is allowed, False if the breaker is tripped.
        """
        limit = self.limits.get(action_kind)
        if limit is None:
            raise ValueError(f"Unknown action kind: {action_kind}")

        count = await self._count_today(action_kind)
        is_allowed = count < limit

        if not is_allowed:
            self._logger.warning(
                "Circuit breaker tripped", action_kind=action_kind, count=count, limit=limit
            )

        return is_allowed

    async def get_status(self) -> dict[str, Any]:
        """Get the current state of the circuit breaker.

        Returns:
            Dict containing today's counts and the configured limits.
        """
        counts = {kind: await self._count_today(kind) for kind in self.limits}
        return {
            "action_counts": counts,
            "limits": dict(self.limits),
            "tripped": {kind: counts[kind] >= limit for kind, limit in self.limits.items()},
        }
