"""Salary band prediction module."""

from __future__ import annotations

import re
import structlog
from typing import Any

logger = structlog.get_logger(__name__)

# Cost-of-living multipliers applied to the Indian base bands.
# Matched on whole tokens, never substrings: a plain `"us" in location`
# test also fires on "Australia", "Belarus" and "Mauritius", tripling those
# salaries and pushing the jobs into Tier 1 on inflated expected value.
LOCATION_MULTIPLIERS: tuple[tuple[frozenset[str], float], ...] = (
    (frozenset({"singapore", "sg"}), 1.3),
    (frozenset({"us", "usa", "united states", "u.s.", "u.s.a."}), 3.0),
)

DEFAULT_LOCATION_MULTIPLIER = 1.0  # India

_TOKEN_RE = re.compile(r"[a-z.]+")


def _location_multiplier(location: str) -> float:
    """Resolve a location string to its cost-of-living multiplier."""
    text = location.lower()
    tokens = set(_TOKEN_RE.findall(text))

    for names, multiplier in LOCATION_MULTIPLIERS:
        # Match a whole token ("us") or a multi-word name ("united states").
        if tokens & names or any(" " in name and name in text for name in names):
            return multiplier

    return DEFAULT_LOCATION_MULTIPLIER


def predict_salary_band(title: str, location: str, yoe: int) -> dict[str, Any]:
    """
    Predict a salary band based on title, location, and years of experience.
    
    Cold start uses hardcoded Indian tech salary bands by seniority.
    Location adjustments: India=1.0, Singapore=1.3, US=3.0.
    """
    # Hardcoded Indian tech salary bands based on YoE
    if yoe < 3:
        base_p50 = 1500000.0  # INR
    elif yoe < 7:
        base_p50 = 3000000.0
    else:
        base_p50 = 5000000.0
        
    p25 = base_p50 * 0.8
    p75 = base_p50 * 1.2
    
    loc_multiplier = _location_multiplier(location)

    band = {
        "p25": p25 * loc_multiplier,
        "p50": base_p50 * loc_multiplier,
        "p75": p75 * loc_multiplier,
        "currency": "INR",
        "source": "cold_start_model",
    }
    
    logger.info("predicted_salary_band", title=title, location=location, yoe=yoe, multiplier=loc_multiplier)
    return band
