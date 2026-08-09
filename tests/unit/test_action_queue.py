import pytest
from datetime import datetime, timedelta, timezone

from jobos.action_queue.priority import calculate_priority

def test_calculate_priority_high_ev():
    """Test high EV score gives higher priority."""
    deadline = datetime.now(timezone.utc) + timedelta(days=5)
    
    low_ev_score = calculate_priority("apply", ev_score=0.2, deadline=deadline, tier=2)
    high_ev_score = calculate_priority("apply", ev_score=0.9, deadline=deadline, tier=2)
    
    assert high_ev_score > low_ev_score

def test_calculate_priority_deadline_proximity():
    """Test deadline proximity boosts priority."""
    now = datetime.now(timezone.utc)
    far_deadline = now + timedelta(days=15)
    close_deadline = now + timedelta(days=1)
    
    far_priority = calculate_priority("apply", ev_score=0.5, deadline=far_deadline, tier=2)
    close_priority = calculate_priority("apply", ev_score=0.5, deadline=close_deadline, tier=2)
    
    assert close_priority > far_priority

def test_calculate_priority_tier_1_boost():
    """Test Tier 1 gets priority boost."""
    deadline = datetime.now(timezone.utc) + timedelta(days=5)
    
    tier_2_score = calculate_priority("apply", ev_score=0.5, deadline=deadline, tier=2)
    tier_1_score = calculate_priority("apply", ev_score=0.5, deadline=deadline, tier=1)
    
    assert tier_1_score > tier_2_score
