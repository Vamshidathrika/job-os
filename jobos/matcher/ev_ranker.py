"""Expected Value (EV) Ranker module."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def calculate_ev(p_offer: float, predicted_comp_p50: float, p_accept: float = 0.85) -> float:
    """
    Calculates the Expected Value (EV) of a job opportunity.
    
    Formula from v2 §5.1: EV = P(offer | profile, role) * predicted_comp * P(accept)
    
    Args:
        p_offer: The probability of receiving an offer given the profile and role.
        predicted_comp_p50: The predicted compensation (p50).
        p_accept: The probability of the candidate accepting the offer (default 0.85).
        
    Returns:
        float: The expected value.
    """
    ev = p_offer * predicted_comp_p50 * p_accept
    
    logger.debug(
        "Calculated EV",
        p_offer=p_offer,
        predicted_comp_p50=predicted_comp_p50,
        p_accept=p_accept,
        ev=ev
    )
    
    return ev


def rank_jobs_by_ev(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sorts a list of job matches by their Expected Value (EV) in descending order.
    
    Expected to have an 'ev' key calculated within the dict.
    If 'ev' is missing, it will be treated as 0.0.
    
    Args:
        matches: A list of dictionaries representing job matches.
        
    Returns:
        list[dict[str, Any]]: The list of matches sorted by EV descending.
    """
    sorted_matches = sorted(
        matches,
        key=lambda match: match.get("ev", match.get("ev_score", 0.0)),
        reverse=True,
    )
    
    logger.info("Ranked jobs by EV", match_count=len(matches))
    
    return sorted_matches
