"""Band-aware action queue for JOBOS.

Backed by the action_queue table so queued work survives a restart and is
visible across processes. Every statement runs on a caller-supplied,
tenant-scoped connection, so RLS confines each tenant to its own rows.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Band A = auto-execute, B = user review queue, C = human-only escalation.
VALID_BANDS = ("A", "B", "C")


class ActionQueue:
    """Action queue for a specific tenant."""

    def __init__(self, conn: Any, tenant_id: str) -> None:
        """Initialize for tenant.

        Args:
            conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn).
            tenant_id: The tenant whose rows this queue reads and writes.
        """
        self.conn = conn
        self.tenant_id = tenant_id

    async def enqueue(self, action_type: str, payload: dict[str, Any], band: str) -> str:
        """Enqueue an action, returns action_id. Band='A' (auto), 'B' (review queue), 'C' (human only)."""
        if band not in VALID_BANDS:
            raise ValueError(f"Invalid band {band!r}; expected one of {VALID_BANDS}")

        action_id = await self.conn.fetchval(
            """
            INSERT INTO action_queue (user_id, action_type, payload, band)
            VALUES ($1, $2, $3::jsonb, $4)
            RETURNING id
            """,
            uuid.UUID(str(self.tenant_id)),
            action_type,
            json.dumps(payload),
            band,
        )
        logger.info("action_enqueued", action_id=str(action_id), band=band, action_type=action_type)
        return str(action_id)

    async def dequeue_batch(self, band: str, limit: int = 10) -> list[dict[str, Any]]:
        """Claim the next batch of pending actions for a band.

        Uses SKIP LOCKED so concurrent workers never hand the same action to
        two executors.
        """
        rows = await self.conn.fetch(
            """
            UPDATE action_queue SET status = 'processing', updated_at = now()
            WHERE id IN (
                SELECT id FROM action_queue
                WHERE band = $1 AND status = 'pending'
                ORDER BY created_at
                LIMIT $2
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, action_type, payload, band, status
            """,
            band,
            limit,
        )
        return [
            {
                "action_id": str(row["id"]),
                "action_type": row["action_type"],
                "payload": json.loads(row["payload"]),
                "band": row["band"],
                "status": row["status"],
                "tenant_id": self.tenant_id,
            }
            for row in rows
        ]

    async def mark_complete(self, action_id: str, result: dict[str, Any]) -> None:
        """Mark action done."""
        await self.conn.execute(
            """
            UPDATE action_queue
            SET status = 'completed', result = $2::jsonb, error = NULL, updated_at = now()
            WHERE id = $1
            """,
            uuid.UUID(action_id),
            json.dumps(result),
        )
        logger.info("action_completed", action_id=action_id)

    async def mark_failed(self, action_id: str, error: str) -> None:
        """Mark action failed."""
        await self.conn.execute(
            """
            UPDATE action_queue
            SET status = 'failed', error = $2, updated_at = now()
            WHERE id = $1
            """,
            uuid.UUID(action_id),
            error,
        )
        logger.error("action_failed", action_id=action_id, error=error)

    async def escalate(self, action_id: str) -> None:
        """Move an action to the human-only band and return it to pending."""
        await self.conn.execute(
            """
            UPDATE action_queue
            SET band = 'C', status = 'pending', updated_at = now()
            WHERE id = $1
            """,
            uuid.UUID(action_id),
        )
        logger.info("action_escalated_to_band_c", action_id=action_id)

    async def count_actions_since(self, action_type: str, days: int = 1) -> int:
        """Count non-failed actions of a type in the recent window.

        Used by the circuit breaker to enforce real daily caps against
        persisted history rather than per-process counters. The window is
        passed as a bound parameter via make_interval — never interpolated.
        """
        return await self.conn.fetchval(
            """
            SELECT count(*) FROM action_queue
            WHERE action_type = $1
              AND status <> 'failed'
              AND created_at > now() - make_interval(days => $2)
            """,
            action_type,
            days,
        )
