"""Tier classification module."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def classify_tier(match_score: float, ev_score: float, company_tier: int = 2) -> int:
    """
    Classifies jobs into Tier 1, Tier 2, or Tier 3 based on match score and expected value.
    
    Tier 1: match_score >= 0.65 and ev_score >= 0.60 (High EV -> triggers 7-Day Warm Path Race).
    Tier 2: match_score >= 0.50 (Standard application).
    Tier 3: Low EV / low score (Auto-filtered or Band A cold apply).
    
    Args:
        match_score: The calculated match score for the job and candidate.
        ev_score: The expected value score.
        company_tier: The tier of the company (default 2).
        
    Returns:
        int: The classification tier (1, 2, or 3).
    """
    if match_score >= 0.65 and ev_score >= 0.60:
        tier = 1
    elif match_score >= 0.50:
        tier = 2
    else:
        tier = 3
        
    logger.debug(
        "Classified job tier",
        match_score=match_score,
        ev_score=ev_score,
        company_tier=company_tier,
        assigned_tier=tier
    )
    
    return tier
