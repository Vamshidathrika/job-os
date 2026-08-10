"""Thin wrapper around the Composio SDK.

Centralises toolset construction and error handling so the individual
integrations (Gmail, Calendar, LinkedIn) do not each re-implement the same
credential plumbing and failure semantics.

Composio's SDK is synchronous; every call is pushed to a worker thread so it
never blocks the event loop that the rest of JOBOS runs on.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from jobos.config import Settings, settings as default_settings

logger = structlog.get_logger(__name__)


class ComposioNotConfiguredError(RuntimeError):
    """Raised when a Composio call is attempted without an API key."""


class ComposioActionError(RuntimeError):
    """Raised when Composio reports that an action did not succeed."""


class ComposioClient:
    """Per-tenant Composio action executor.

    Args:
        tenant_id: Used as Composio's entity_id, which is what scopes the
            connected accounts (a tenant's own Gmail/Calendar/LinkedIn) to
            that tenant.
        settings: Application settings; defaults to the global singleton.
    """

    def __init__(self, tenant_id: str, settings: Settings | None = None) -> None:
        self.tenant_id = tenant_id
        self.settings = settings or default_settings
        self._toolset: Any = None
        self._logger = logger.bind(tenant_id=tenant_id)

    @property
    def is_configured(self) -> bool:
        """Whether a Composio API key is present."""
        return bool(self.settings.composio.api_key)

    def _get_toolset(self) -> Any:
        """Build (once) the ComposioToolSet bound to this tenant's entity."""
        if self._toolset is None:
            if not self.is_configured:
                raise ComposioNotConfiguredError(
                    "JOBOS_COMPOSIO_API_KEY is not set — cannot reach Composio. "
                    "Add the key to enable Gmail/Calendar/LinkedIn actions."
                )
            from composio import ComposioToolSet

            self._toolset = ComposioToolSet(
                api_key=self.settings.composio.api_key,
                entity_id=self.tenant_id,
            )
        return self._toolset

    async def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a Composio action and return its data payload.

        Raises:
            ComposioNotConfiguredError: if no API key is configured.
            ComposioActionError: if Composio reports failure. Failures are
                raised rather than returned so a caller can never mistake an
                unsent email for a sent one.
        """
        toolset = self._get_toolset()

        def _call() -> dict[str, Any]:
            return toolset.execute_action(
                action=action, params=params, entity_id=self.tenant_id
            )

        self._logger.info("composio_action_start", action=action)
        response = await asyncio.to_thread(_call)

        # Composio returns {"successful": bool, "data": {...}, "error": ...}.
        # Older/edge responses may omit the flag, so treat a present error as
        # failure too rather than assuming success.
        if isinstance(response, dict):
            succeeded = response.get("successful", response.get("successfull"))
            error = response.get("error")
            if succeeded is False or (succeeded is None and error):
                self._logger.error("composio_action_failed", action=action, error=str(error))
                raise ComposioActionError(f"Composio action {action} failed: {error}")
            data = response.get("data")
            self._logger.info("composio_action_ok", action=action)
            return data if isinstance(data, dict) else {"data": data}

        return {"data": response}
