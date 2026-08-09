"""Shadow mode controller for JOBOS."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ShadowMode:
    """Controls shadow mode for a tenant, where actions are proposed but not executed."""

    def __init__(self, tenant_id: str) -> None:
        """
        Initialize the shadow mode controller for a tenant.

        Args:
            tenant_id (str): The unique identifier for the tenant.
        """
        self.tenant_id = tenant_id
        self._enabled = True
        logger.info("shadow_mode_initialized", tenant_id=tenant_id)

    async def enable(self) -> None:
        """Enable shadow mode for the tenant."""
        self._enabled = True
        logger.info("shadow_mode_enabled", tenant_id=self.tenant_id)

    async def disable(self) -> None:
        """Disable shadow mode for the tenant (full autopilot)."""
        self._enabled = False
        logger.info("shadow_mode_disabled", tenant_id=self.tenant_id)

    async def get_proposed_actions(self) -> list[dict[str, Any]]:
        """
        Get actions the system proposes to take.

        Returns:
            list[dict[str, Any]]: A list of proposed actions.
        """
        logger.debug("fetching_proposed_actions", tenant_id=self.tenant_id)
        # Mock proposed actions
        return []

    async def approve_action(self, action_id: str) -> dict[str, Any]:
        """
        Approve a proposed action for execution.

        Args:
            action_id (str): The unique identifier of the action to approve.

        Returns:
            dict[str, Any]: The result of the approved action execution.
        """
        logger.info("action_approved", tenant_id=self.tenant_id, action_id=action_id)
        return {"status": "approved", "action_id": action_id}

    async def reject_action(self, action_id: str, reason: str) -> None:
        """
        Reject a proposed action with feedback for calibration.

        Args:
            action_id (str): The unique identifier of the action to reject.
            reason (str): The reason for rejecting the action.
        """
        logger.info(
            "action_rejected",
            tenant_id=self.tenant_id,
            action_id=action_id,
            reason=reason,
        )
