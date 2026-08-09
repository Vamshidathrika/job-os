"""Allowlist-based credential scrubber for logging boundaries."""

from __future__ import annotations

import re
from typing import Any
import structlog

# Regex patterns matching API keys, tokens, and secrets.
# This is the LOGGING BOUNDARY — if a pattern isn't here, it can leak.
# Allowlist approach: we scrub aggressively. False positives are acceptable;
# false negatives (leaked credentials) are not.
CREDENTIAL_PATTERNS: list[re.Pattern[str]] = [
    # OpenRouter
    re.compile(r"sk-or-v1-[a-zA-Z0-9]{20,}"),
    # Groq
    re.compile(r"gsk_[a-zA-Z0-9\-_]{16,}"),
    # OpenAI / generic sk-
    re.compile(r"sk-proj-[a-zA-Z0-9\-_]{20,}"),
    re.compile(r"sk-[a-zA-Z0-9]{32,}"),
    # Bearer tokens (OAuth, JWT)
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    # Google OAuth access tokens
    re.compile(r"ya29\.[a-zA-Z0-9\-_]{20,}"),
    # AWS access keys
    re.compile(r"AKIA[0-9A-Z]{16}"),
    # LinkedIn tokens
    re.compile(r"AQV[a-zA-Z0-9\-._]{20,}"),
    # NVIDIA NIM / API keys
    re.compile(r"nvapi-[a-zA-Z0-9\-_]{20,}"),
    # Composio keys
    re.compile(r"comp-[a-zA-Z0-9]{20,}"),
    # Apollo keys (generic long alphanumeric)
    re.compile(r"[a-zA-Z0-9]{40,64}(?=[\s\"',}\\])"),
    # Generic hex secrets (64+ chars, likely a key)
    re.compile(r"[0-9a-f]{64,}"),
    # Base64-encoded tokens (long base64 blobs — aggressive but safe)
    re.compile(r"eyJ[a-zA-Z0-9\-_]{50,}"),
]

# Field names that are safe to log
SAFE_LOG_FIELDS: frozenset[str] = frozenset([
    "module", "action", "user_id", "job_id", "tenant_id", "timestamp", "status", "level"
])


def scrub(data: Any) -> Any:
    """Recursively walks data and replaces anything matching credential patterns with [REDACTED]."""
    if isinstance(data, dict):
        return {k: scrub(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [scrub(item) for item in data]
    elif isinstance(data, str):
        scrubbed = data
        for pattern in CREDENTIAL_PATTERNS:
            scrubbed = pattern.sub("[REDACTED]", scrubbed)
        return scrubbed
    else:
        return data


def _scrub_event_dict(
    logger: structlog.types.WrappedLogger, 
    method_name: str, 
    event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Structlog processor to scrub credentials from logs."""
    for key, value in list(event_dict.items()):
        if key not in SAFE_LOG_FIELDS:
            event_dict[key] = scrub(value)
    return event_dict


def install_log_scrubber() -> None:
    """Installs the scrubber as a structlog processor."""
    structlog.configure(
        processors=[
            _scrub_event_dict,
            structlog.dev.ConsoleRenderer()
        ]
    )
