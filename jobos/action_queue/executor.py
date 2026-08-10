"""Action executor for executing actions from the queue."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import structlog

from .queue import ActionQueue

logger = structlog.get_logger(__name__)

# An action handler receives the action's payload and returns a result dict
# that is persisted alongside the completed action.
ActionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class UnknownActionTypeError(LookupError):
    """Raised when no handler is registered for an action type."""


class ActionExecutor:
    """Executes actions from the ActionQueue via registered handlers."""

    def __init__(self, queue: ActionQueue, handlers: dict[str, ActionHandler] | None = None) -> None:
        """Initialize with queue and the handler registry.

        Handlers are injected rather than imported here so the executor stays
        independent of which integrations are wired up (and so tests can
        substitute a handler without patching module internals).
        """
        self.queue = queue
        self.handlers: dict[str, ActionHandler] = dict(handlers or {})

    def register(self, action_type: str, handler: ActionHandler) -> None:
        """Register a handler for an action type."""
        self.handlers[action_type] = handler

    async def process_band_a(self, limit: int = 10) -> dict[str, int]:
        """Auto-execute Band A actions.

        Returns:
            Counts of executed/failed actions, so a run where everything
            failed is distinguishable from a run with nothing to do.
        """
        actions = await self.queue.dequeue_batch(band="A", limit=limit)
        executed = failed = 0

        for action in actions:
            action_id = action["action_id"]
            action_type = action["action_type"]
            try:
                handler = self.handlers.get(action_type)
                if handler is None:
                    raise UnknownActionTypeError(
                        f"No handler registered for action type {action_type!r}"
                    )
                logger.info("executing_band_a_action", action_id=action_id, action_type=action_type)
                result = await handler(action["payload"])
                await self.queue.mark_complete(action_id, result=result)
                executed += 1
            except Exception as e:
                # Persist the failure rather than dropping it: an action that
                # errors must be visible for retry/escalation, not silently lost.
                failed += 1
                await self.queue.mark_failed(action_id, error=str(e))

        if actions and not executed:
            logger.error("band_a_batch_total_failure", attempted=len(actions), failed=failed)
        return {"executed": executed, "failed": failed}

    async def present_band_b(self, limit: int = 10) -> list[dict[str, Any]]:
        """Return Band B actions for user review."""
        actions = await self.queue.dequeue_batch(band="B", limit=limit)
        logger.info("presenting_band_b_actions", count=len(actions))
        return actions

    async def escalate_band_c(self, action_id: str) -> None:
        """Send to human queue."""
        await self.queue.escalate(action_id)
