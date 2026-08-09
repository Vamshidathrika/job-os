"""Warm-Path channel definitions and configuration."""

from __future__ import annotations

from enum import Enum
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


class WarmPathChannel(str, Enum):
    """Enumeration of available warm path channels."""
    REFERRAL = "referral"
    RECRUITER = "recruiter"
    SIGNAL = "signal"


def get_channel_config(channel: WarmPathChannel) -> dict[str, Any]:
    """Retrieves channel-specific configurations.
    
    Args:
        channel: The channel to get config for.
        
    Returns:
        A dictionary containing max touches, delay, and fallback rules.
    """
    configs = {
        WarmPathChannel.REFERRAL: {
            "max_touches": 3,
            "delay_days": 2,
            "fallback_rule": "auto_cold"
        },
        WarmPathChannel.RECRUITER: {
            "max_touches": 2,
            "delay_days": 3,
            "fallback_rule": "manual_review"
        },
        WarmPathChannel.SIGNAL: {
            "max_touches": 1,
            "delay_days": 1,
            "fallback_rule": "auto_cold"
        }
    }
    logger.info("fetched_channel_config", channel=channel.value)
    return configs.get(channel, {})
