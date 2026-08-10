"""Handlers the ActionExecutor dispatches to, by action_type.

Handlers are built per request rather than registered globally so each one
closes over the tenant-scoped connection that RLS requires.
"""

from __future__ import annotations

from typing import Any

import structlog

from jobos.outbox import send_email_guarded

logger = structlog.get_logger(__name__)


def build_handlers(
    conn: Any, tenant_id: str, gmail: Any | None = None
) -> dict[str, Any]:
    """Build the action_type -> handler map for one tenant.

    Args:
        conn: A tenant-scoped connection.
        tenant_id: The acting tenant.
        gmail: A GmailClient; constructed per tenant if omitted.
    """
    if gmail is None:
        from jobos.integrations.gmail import GmailClient

        gmail = GmailClient(tenant_id=tenant_id)

    async def referral_touch(payload: dict[str, Any]) -> dict[str, Any]:
        """Send one touch of an outreach sequence via the guarded send path."""
        recipient = payload.get("to")
        if not recipient:
            # Better to fail the action than to send nowhere and mark it done.
            raise ValueError("referral_touch payload has no 'to' address")

        return await send_email_guarded(
            conn,
            gmail,
            tenant_id=tenant_id,
            to=recipient,
            subject=payload.get("subject", ""),
            body=payload.get("body", ""),
        )

    async def submit_application(payload: dict[str, Any]) -> dict[str, Any]:
        """Cold apply is not implemented; refuse rather than claim success."""
        from jobos.cold_apply.executor import ColdApplyExecutor

        executor = ColdApplyExecutor(tenant_id=tenant_id)
        return await executor.submit_application(payload.get("job_url", ""), dry_run=False)

    async def publish_post(payload: dict[str, Any]) -> dict[str, Any]:
        """LinkedIn publishing is not wired up yet."""
        raise NotImplementedError(
            "Publishing is not implemented: it needs a LinkedIn connected account "
            "via Composio. Refusing rather than marking the post as published."
        )

    return {
        "referral_touch": referral_touch,
        "submit_application": submit_application,
        "publish_post": publish_post,
    }
