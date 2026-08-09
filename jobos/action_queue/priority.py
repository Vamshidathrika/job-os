"""Priority calculation for queued actions."""

from __future__ import annotations

from datetime import datetime, timezone
import structlog

logger = structlog.get_logger(__name__)


def calculate_priority(action_type: str, ev_score: float, deadline: datetime | None, tier: int) -> float:
    """
    Calculate priority score. Higher = more urgent.
    
    Factors: EV score, deadline proximity, tier level.
    """
    base_score = ev_score * 100.0

    # Tier multiplier (lower tier number = higher priority, usually Tier 1 > Tier 2)
    tier_multiplier = 1.0
    if tier == 1:
        tier_multiplier = 1.5
    elif tier == 2:
        tier_multiplier = 1.2
    elif tier == 3:
        tier_multiplier = 1.0
    elif tier > 3:
        tier_multiplier = 0.8
        
    base_score *= tier_multiplier

    # Deadline factor
    if deadline:
        now = datetime.now(timezone.utc)
        if deadline > now:
            days_left = (deadline - now).days
            if days_left == 0:
                base_score *= 2.0  # urgent
            elif days_left < 3:
                base_score *= 1.5
            elif days_left > 14:
                base_score *= 0.8
        else:
            # Overdue
            base_score *= 3.0
            
    logger.debug("calculated_priority", action_type=action_type, score=base_score)
    return base_score
