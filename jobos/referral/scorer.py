"""Referrer quality scoring."""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)

def score_referrer(referrer: dict[str, Any], user_profile: dict[str, Any]) -> float:
    """
    Scoring weights: shared school (+0.3), shared past company (+0.4), same department (+0.2), seniority match (+0.1).
    Returns 0.0 to 1.0 score.
    """
    score = 0.0
    
    if referrer.get("shared_school"):
        score += 0.3
    if referrer.get("shared_past_company"):
        score += 0.4
    if referrer.get("same_department"):
        score += 0.2
    if referrer.get("seniority_match"):
        score += 0.1
        
    return min(score, 1.0)
