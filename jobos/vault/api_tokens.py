"""Opaque bearer tokens that authenticate API callers.

Tenant identity is derived from a secret the caller proves they hold, never
from a header they merely assert.

Opaque-and-hashed rather than JWT on purpose: revocation must take effect on
the very next request. A signed token cannot be withdrawn without a denylist,
which reintroduces the database lookup that statelessness was meant to avoid
while adding key management on top.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

TOKEN_PREFIX = "jobos_"

# 32 bytes of urandom, URL-safe encoded. Wide enough that guessing is
# hopeless and the value survives being pasted through a shell or a browser.
TOKEN_SECRET_BYTES = 32


class InvalidTokenError(PermissionError):
    """Raised when a bearer token is malformed, unknown, or revoked."""


def _hash(token: str) -> str:
    """Hash a token for storage and lookup.

    Plain SHA-256, not a password KDF: this is a 256-bit random secret, not a
    human-chosen password, so there is no dictionary to attack and stretching
    would only slow down every request.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_token(
    conn: Any, user_id: str, name: str, expires_in_days: int | None = None
) -> str:
    """Mint a token for a tenant and return the plaintext, once.

    The plaintext is never stored and cannot be recovered — if it is lost,
    revoke this one and mint another.

    Args:
        conn: A connection; api_tokens has no RLS (see jobos/db/models.py).
        user_id: The tenant this token acts as.
        name: Human label, e.g. "vamshi laptop", so it can be revoked by sight.
        expires_in_days: If given, the token stops resolving after this many
            days (a negative value produces an already-expired token, useful
            for tests). Default is None — the token never expires, matching
            the behavior before this parameter existed.

    Returns:
        The plaintext token, prefixed for recognisability in logs and configs.
    """
    if not name.strip():
        raise ValueError("A token name is required so it can be revoked later")

    token = f"{TOKEN_PREFIX}{secrets.token_urlsafe(TOKEN_SECRET_BYTES)}"
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        if expires_in_days is not None
        else None
    )

    await conn.execute(
        """
        INSERT INTO api_tokens (user_id, token_hash, name, expires_at)
        VALUES ($1::uuid, $2, $3, $4)
        ON CONFLICT (user_id, name) DO UPDATE
            SET token_hash = EXCLUDED.token_hash,
                created_at = now(),
                last_used_at = NULL,
                revoked_at = NULL,
                expires_at = EXCLUDED.expires_at
        """,
        user_id,
        _hash(token),
        name,
        expires_at,
    )
    logger.info("api_token_created", user_id=user_id, name=name)
    return token


async def _record_audit(
    conn: Any, *, user_id: str | None, token_hash: str, success: bool, ip_address: str | None
) -> None:
    """Insert one row into api_token_audit for an authentication attempt.

    Never logs the raw plaintext token — only its SHA-256, which is already
    what the caller looked the token up by.
    """
    await conn.execute(
        """
        INSERT INTO api_token_audit (user_id, token_hash, success, ip_address)
        VALUES ($1::uuid, $2, $3, $4)
        """,
        user_id,
        token_hash,
        success,
        ip_address,
    )


async def resolve_tenant(conn: Any, token: str, ip_address: str | None = None) -> str:
    """Resolve a bearer token to the tenant it authenticates.

    Args:
        conn: A connection; api_tokens/api_token_audit have no RLS.
        token: The bearer token presented by the caller.
        ip_address: The caller's source IP, recorded on the audit row only
            (never used to authenticate). Optional so existing two-argument
            callers are unaffected.

    Every attempt — success or failure — is recorded in api_token_audit
    before returning or raising, in addition to last_used_at being bumped on
    success.

    Raises:
        InvalidTokenError: if the token is malformed, unknown or revoked.
            All three fail identically so a caller cannot probe for which
            tokens exist.
    """
    candidate = (token or "").strip()
    token_hash = _hash(candidate)

    if not candidate.startswith(TOKEN_PREFIX) or len(candidate) <= len(TOKEN_PREFIX):
        await _record_audit(
            conn, user_id=None, token_hash=token_hash, success=False, ip_address=ip_address
        )
        raise InvalidTokenError("Malformed API token")

    row = await conn.fetchrow(
        """
        UPDATE api_tokens
        SET last_used_at = now()
        WHERE token_hash = $1 AND revoked_at IS NULL
          AND (expires_at IS NULL OR expires_at > now())
        RETURNING user_id
        """,
        token_hash,
    )
    if row is None:
        logger.warning("api_token_rejected")
        await _record_audit(
            conn, user_id=None, token_hash=token_hash, success=False, ip_address=ip_address
        )
        raise InvalidTokenError("Unknown or revoked API token")

    await _record_audit(
        conn, user_id=row["user_id"], token_hash=token_hash, success=True, ip_address=ip_address
    )
    return str(row["user_id"])


async def revoke_token(conn: Any, user_id: str, name: str) -> bool:
    """Revoke a tenant's token by name. Returns whether one was revoked."""
    revoked = await conn.fetchval(
        """
        UPDATE api_tokens
        SET revoked_at = now()
        WHERE user_id = $1::uuid AND name = $2 AND revoked_at IS NULL
        RETURNING id
        """,
        user_id,
        name,
    )
    logger.info("api_token_revoked", user_id=user_id, name=name, found=revoked is not None)
    return revoked is not None


async def list_tokens(conn: Any, user_id: str) -> list[dict[str, Any]]:
    """List a tenant's tokens. Never returns anything usable as a credential."""
    rows = await conn.fetch(
        """
        SELECT name, created_at, last_used_at, revoked_at
          FROM api_tokens
         WHERE user_id = $1::uuid
         ORDER BY created_at DESC
        """,
        user_id,
    )
    return [dict(row) for row in rows]
