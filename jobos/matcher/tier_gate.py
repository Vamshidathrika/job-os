"""Tier classification module."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def classify_tier(match_score: float, ev_score: float, has_warm_contact: bool = False) -> int:
    """
    Tier 1 (triggers the 7-day warm-path race): match_score >= 0.65 and
    ev_score >= 0.60 OR, when a real warm connection exists at the company,
    the lower bar match_score >= 0.50 and ev_score >= 0.40 — referred
    applicants convert at 4-10x cold applies, so a real connection is worth
    more than marginal comp/similarity headroom (see docs/superpowers/plans/
    2026-08-12-matching-relevance-fixes.md for the evidence this is based on).
    Tier 2: match_score >= 0.50 (no warm path). Tier 3: everything else.

    Args:
        match_score: The calculated match score for the job and candidate.
        ev_score: The expected value score.
        has_warm_contact: Whether the user has a real warm connection at the
            hiring company (see jobos.referral.network_mapper.map_existing_network).

    Returns:
        int: The classification tier (1, 2, or 3).
    """
    if has_warm_contact and match_score >= 0.50 and ev_score >= 0.40:
        tier = 1
    elif match_score >= 0.65 and ev_score >= 0.60:
        tier = 1
    elif match_score >= 0.50:
        tier = 2
    else:
        tier = 3

    logger.debug(
        "classified_job_tier",
        match_score=match_score,
        ev_score=ev_score,
        has_warm_contact=has_warm_contact,
        assigned_tier=tier,
    )

    return tier
