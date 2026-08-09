"""Decision matrix for the Warm-Path race engine."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def should_hold_application(match_score: float, ev_score: float, tier: int) -> bool:
    """Determines if a job application should be held for a warm path.
    
    Args:
        match_score: Score representing how well the candidate matches the job.
        ev_score: Expected value score for the job.
        tier: Job tier (1 is highest priority).
        
    Returns:
        True if job is Tier 1 (hold for warm path), False for immediate cold apply.
    """
    decision = tier == 1
    logger.info(
        "evaluated_hold_decision",
        match_score=match_score,
        ev_score=ev_score,
        tier=tier,
        decision=decision
    )
    return decision


def select_fallback_band(days_elapsed: int, warm_responses: int) -> str:
    """Selects the fallback band based on race state.
    
    Args:
        days_elapsed: Number of days the race has been running.
        warm_responses: Number of warm responses received.
        
    Returns:
        'A' (auto-apply), 'B' (queue for review), or 'C' (human only).
    """
    if warm_responses > 0:
        band = "C"
    elif days_elapsed >= 7:
        band = "A"
    else:
        band = "B"
        
    logger.info(
        "selected_fallback_band",
        days_elapsed=days_elapsed,
        warm_responses=warm_responses,
        band=band
    )
    return band
