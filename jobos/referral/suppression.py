"""Global suppression list enforcement."""

from __future__ import annotations

import asyncpg
import structlog

from jobos.policy.compliance import hash_email_for_suppression

logger = structlog.get_logger(__name__)

# Why an address was suppressed. Kept as plain strings so the reason survives
# in the table for audit without needing a join.
REASON_UNSUBSCRIBED = "unsubscribed"
REASON_BOUNCED = "bounced"
REASON_COMPLAINED = "spam_complaint"
REASON_MANUAL = "manual"

DEFAULT_SUPPRESSION_REASON = REASON_UNSUBSCRIBED


async def check_suppression(conn: asyncpg.Connection, email: str) -> bool:
    """Returns True if email hash exists in global suppression table.

    The list is global on purpose: someone who opted out of one tenant's
    outreach must not be contacted by another tenant either.
    """
    email_hash = hash_email_for_suppression(email)

    query = "SELECT 1 FROM suppression_list WHERE email_hash = $1"
    result = await conn.fetchval(query, email_hash)

    is_suppressed = result is not None
    if is_suppressed:
        logger.info("Email found in suppression list")

    return is_suppressed


async def add_to_suppression(
    conn: asyncpg.Connection, email: str, reason: str = DEFAULT_SUPPRESSION_REASON
) -> None:
    """Adds an email hash to the global suppression list.

    Args:
        conn: The database connection.
        email: The address to suppress; only its SHA-256 hash is stored.
        reason: Why it was suppressed. Required by the schema — omitting it
            previously made every call fail with a NOT NULL violation, so no
            opt-out was ever actually recorded.
    """
    if not reason:
        raise ValueError("A suppression reason is required")

    email_hash = hash_email_for_suppression(email)

    query = (
        "INSERT INTO suppression_list (email_hash, reason) VALUES ($1, $2) "
        "ON CONFLICT (email_hash) DO NOTHING"
    )
    await conn.execute(query, email_hash, reason)
    logger.info("Added email to suppression list", reason=reason)
