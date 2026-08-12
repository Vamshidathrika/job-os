"""Rate limiting for repeated failed authentication attempts.

Counts are read from the persisted auth_failures table rather than kept in
memory: an in-process counter resets to zero on every restart or extra
worker, which silently voids the cap it is supposed to enforce. Modeled on
jobos.calibration.circuit_breaker.CircuitBreaker's "count real persisted
rows" pattern.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Failures allowed from one IP within the window before further attempts are
# blocked outright.
MAX_FAILURES = 5
WINDOW_MINUTES = 15


async def is_rate_limited(conn: Any, ip_address: str | None) -> bool:
    """Return True if this IP has too many recent failed auth attempts.

    Args:
        conn: A global (non-tenant-scoped) connection — auth_failures has no
            RLS, same reasoning as api_tokens: authentication must resolve
            before any tenant context exists to filter by.
        ip_address: The caller's source IP. None means the deployment (or a
            test harness) could not determine a client address; rather than
            lumping every such caller into one shared bucket that unrelated
            traffic could trip, or crashing on a missing value, we simply
            don't rate-limit requests we can't attribute to an IP.
    """
    if ip_address is None:
        return False

    count = await conn.fetchval(
        """
        SELECT count(*) FROM auth_failures
        WHERE ip_address = $1
          AND attempted_at > now() - make_interval(mins => $2)
        """,
        ip_address,
        WINDOW_MINUTES,
    )
    return count >= MAX_FAILURES


async def record_failure(conn: Any, ip_address: str | None) -> None:
    """Record a failed authentication attempt for this IP.

    A None ip_address (see is_rate_limited) is not recorded — there is no
    address to attribute the failure to, and it would never be counted
    against anything anyway.
    """
    if ip_address is None:
        return

    await conn.execute(
        "INSERT INTO auth_failures (ip_address) VALUES ($1)",
        ip_address,
    )
    logger.warning("auth_failure_recorded", ip_address=ip_address)
