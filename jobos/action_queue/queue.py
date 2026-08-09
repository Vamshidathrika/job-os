"""Band-aware action queue for JOBOS."""

from __future__ import annotations

import uuid
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


class ActionQueue:
    """Action queue for a specific tenant."""

    def __init__(self, tenant_id: str) -> None:
        """Initialize for tenant."""
        self.tenant_id = tenant_id
        # In-memory mock for now, replace with actual DB interaction
        self._queue: list[dict[str, Any]] = []

    async def enqueue(self, action_type: str, payload: dict[str, Any], band: str) -> str:
        """Enqueue an action, returns action_id. Band='A' (auto), 'B' (review queue), 'C' (human only)."""
        action_id = str(uuid.uuid4())
        action = {
            "action_id": action_id,
            "action_type": action_type,
            "payload": payload,
            "band": band,
            "tenant_id": self.tenant_id,
            "status": "pending",
        }
        self._queue.append(action)
        logger.info("action_enqueued", action_id=action_id, band=band, action_type=action_type)
        return action_id

    async def dequeue_batch(self, band: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get next batch of actions for a band."""
        batch = [a for a in self._queue if a["band"] == band and a["status"] == "pending"][:limit]
        for action in batch:
            action["status"] = "processing"
        return batch

    async def mark_complete(self, action_id: str, result: dict[str, Any]) -> None:
        """Mark action done."""
        for action in self._queue:
            if action["action_id"] == action_id:
                action["status"] = "completed"
                action["result"] = result
                logger.info("action_completed", action_id=action_id)
                break

    async def mark_failed(self, action_id: str, error: str) -> None:
        """Mark action failed."""
        for action in self._queue:
            if action["action_id"] == action_id:
                action["status"] = "failed"
                action["error"] = error
                logger.error("action_failed", action_id=action_id, error=error)
                break
