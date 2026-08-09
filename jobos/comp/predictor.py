"""Salary band prediction module."""

from __future__ import annotations

import structlog
from typing import Any

logger = structlog.get_logger(__name__)


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
    
    loc_multiplier = 1.0
    loc_lower = location.lower()
    
    if "singapore" in loc_lower:
        loc_multiplier = 1.3
    elif "us" in loc_lower or "united states" in loc_lower:
        loc_multiplier = 3.0
    # Assume India is default / 1.0
        
    band = {
        "p25": p25 * loc_multiplier,
        "p50": base_p50 * loc_multiplier,
        "p75": p75 * loc_multiplier,
        "currency": "INR",
        "source": "cold_start_model",
    }
    
    logger.info("predicted_salary_band", title=title, location=location, yoe=yoe, multiplier=loc_multiplier)
    return band
