"""Guarded outbound send path.

Every outbound email must pass through here. The suppression check and the
daily cap are compliance and reputation controls, and a control that callers
can forget to invoke is not a control — so the send itself lives behind them.
"""

from __future__ import annotations

from typing import Any

import structlog

from jobos.calibration.circuit_breaker import CircuitBreaker
from jobos.referral.suppression import check_suppression

logger = structlog.get_logger(__name__)


class SuppressedRecipientError(RuntimeError):
    """Raised when the recipient is on the global suppression list."""


class SendingCapReachedError(RuntimeError):
    """Raised when the tenant's daily email cap is already spent."""


async def send_email_guarded(
    conn: Any,
    gmail: Any,
    tenant_id: str,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> dict[str, str]:
    """Send an email only if it clears the suppression list and daily cap.

    Args:
        conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn).
        gmail: A GmailClient (or anything with the same send_email signature).
        tenant_id: The sending tenant.
        to: Recipient address.
        subject: Email subject.
        body: Email body text.
        reply_to: Optional reply-to address.

    Returns:
        The provider result for the sent message.

    Raises:
        SuppressedRecipientError: recipient has opted out (globally).
        SendingCapReachedError: tenant is at its daily cap.
    """
    log = logger.bind(tenant_id=tenant_id)

    if await check_suppression(conn, to):
        log.warning("send_blocked_recipient_suppressed")
        raise SuppressedRecipientError(
            "Recipient is on the global suppression list and must not be contacted"
        )

    breaker = CircuitBreaker(conn=conn, tenant_id=tenant_id)
    if not await breaker.check("emails"):
        log.warning("send_blocked_daily_cap_reached")
        raise SendingCapReachedError("Daily email cap reached for this tenant")

    result = await gmail.send_email(to=to, subject=subject, body=body, reply_to=reply_to)
    log.info("guarded_email_sent", message_id=result.get("message_id"))
    return result
