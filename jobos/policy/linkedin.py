"""LinkedIn policy enforcement."""

from __future__ import annotations

from typing import Any
import structlog

from jobos.config import settings
from jobos.policy import PolicyViolation

logger = structlog.get_logger(__name__)

NEVER_AUTOMATE: frozenset[str] = frozenset([
    "connection_request",
    "direct_message",
    "profile_view",
])

AUTONOMOUS: frozenset[str] = frozenset([
    "like",
    "comment",
    "post",
])

# Use API_RATE from config.linkedin
API_RATE: dict[str, Any] = settings.linkedin.model_dump()


def assert_action_allowed(action: str) -> None:
    """Raises PolicyViolation if action is in NEVER_AUTOMATE."""
    if action in NEVER_AUTOMATE:
        raise PolicyViolation(f"LinkedIn action '{action}' is strictly prohibited.")
