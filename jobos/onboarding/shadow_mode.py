"""Shadow mode controller for JOBOS."""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

SHADOW = "shadow"
AUTOPILOT = "autopilot"

# Bands that require a human decision while the tenant is in shadow mode.
REVIEW_BANDS = ("B", "C")


class ShadowMode:
    """Controls shadow mode for a tenant, where actions are proposed but not executed.

    State lives in tenants.autonomy_mode rather than on the instance: shadow
    mode is the guardrail that stops a brand-new tenant from sending real
    email for its first week, so it must survive a restart and be identical
    for every worker and request handler.
    """

    def __init__(self, conn: Any, tenant_id: str) -> None:
        """
        Initialize the shadow mode controller for a tenant.

        Args:
            conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn).
            tenant_id (str): The unique identifier for the tenant.
        """
        self.conn = conn
        self.tenant_id = tenant_id
        logger.info("shadow_mode_initialized", tenant_id=tenant_id)

    async def is_enabled(self) -> bool:
        """Whether the tenant is currently in shadow mode.

        Fails safe: an unknown tenant is treated as being in shadow mode
        rather than granted autopilot.
        """
        mode = await self.conn.fetchval(
            "SELECT autonomy_mode FROM tenants WHERE id = $1::uuid", self.tenant_id
        )
        if mode is None:
            logger.warning("tenant_not_found_defaulting_to_shadow", tenant_id=self.tenant_id)
            return True
        return mode != AUTOPILOT

    async def enable(self) -> None:
        """Enable shadow mode for the tenant."""
        await self._set_mode(SHADOW)
        logger.info("shadow_mode_enabled", tenant_id=self.tenant_id)

    async def disable(self) -> None:
        """Disable shadow mode for the tenant (full autopilot)."""
        await self._set_mode(AUTOPILOT)
        logger.info("shadow_mode_disabled", tenant_id=self.tenant_id)

    async def _set_mode(self, mode: str) -> None:
        await self.conn.execute(
            "UPDATE tenants SET autonomy_mode = $2 WHERE id = $1::uuid", self.tenant_id, mode
        )

    async def get_proposed_actions(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get actions the system proposes to take.

        Returns:
            list[dict[str, Any]]: A list of proposed actions.
        """
        logger.debug("fetching_proposed_actions", tenant_id=self.tenant_id)

        rows = await self.conn.fetch(
            """
            SELECT id, action_type, payload, band, created_at
              FROM action_queue
             WHERE status = 'pending' AND band = ANY($1::text[])
             ORDER BY created_at
             LIMIT $2
            """,
            list(REVIEW_BANDS),
            limit,
        )
        return [
            {
                "action_id": str(row["id"]),
                "action_type": row["action_type"],
                "payload": json.loads(row["payload"]),
                "band": row["band"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]

    async def approve_action(self, action_id: str) -> dict[str, Any]:
        """
        Approve a proposed action for execution.

        Moves the action into the auto-execute band so the executor picks it
        up on its next pass.

        Args:
            action_id (str): The unique identifier of the action to approve.

        Returns:
            dict[str, Any]: The result of the approved action execution.
        """
        updated = await self.conn.fetchval(
            """
            UPDATE action_queue
            SET band = 'A', status = 'pending', updated_at = now()
            WHERE id = $1::uuid AND status = 'pending'
            RETURNING id
            """,
            uuid.UUID(action_id),
        )
        if updated is None:
            raise LookupError(f"No pending action {action_id!r} to approve")

        logger.info("action_approved", tenant_id=self.tenant_id, action_id=action_id)
        return {"status": "approved", "action_id": action_id}

    async def reject_action(self, action_id: str, reason: str) -> None:
        """
        Reject a proposed action with feedback for calibration.

        The reason is persisted, not just logged: rejections are the training
        signal the calibration loop uses to stop proposing similar actions.

        Args:
            action_id (str): The unique identifier of the action to reject.
            reason (str): The reason for rejecting the action.
        """
        await self.conn.execute(
            """
            UPDATE action_queue
            SET status = 'rejected', error = $2, updated_at = now()
            WHERE id = $1::uuid
            """,
            uuid.UUID(action_id),
            reason,
        )
        await self.conn.execute(
            """
            INSERT INTO agent_decisions (id, user_id, module, action, inputs, outputs)
            VALUES (gen_random_uuid(), $1::uuid, 'shadow_mode', 'reject_action', $2::jsonb, $3::jsonb)
            """,
            self.tenant_id,
            json.dumps({"action_id": action_id}),
            json.dumps({"reason": reason}),
        )
        logger.info(
            "action_rejected",
            tenant_id=self.tenant_id,
            action_id=action_id,
            reason=reason,
        )
