import pytest
from jobos.calibration.circuit_breaker import CircuitBreaker
from jobos.calibration.ghost_tracker import detect_ghost_jobs

def test_circuit_breaker_allows_under_limit() -> None:
    """Test actions allowed under daily limit."""
    breaker = CircuitBreaker(tenant_id="tenant_123", max_daily_applies=5)
    
    # Do 4 applies
    for _ in range(4):
        breaker.record_action("applies")
        
    assert breaker.check("applies") is True
    status = breaker.get_status()
    assert status["action_counts"]["applies"] == 4

def test_circuit_breaker_blocks_over_limit() -> None:
    """Test actions blocked when limit hit."""
    breaker = CircuitBreaker(tenant_id="tenant_123", max_daily_applies=3)
    
    # Do 3 applies
    for _ in range(3):
        breaker.record_action("applies")
        
    # Check should now be False (since count >= limit)
    assert breaker.check("applies") is False

@pytest.mark.asyncio
async def test_detect_ghost_jobs() -> None:
    """Test ghost detection flags old listings."""
    jobs = [
        {"id": "job_1", "title": "Software Engineer", "days_active": 10},
        {"id": "job_2", "title": "Data Scientist", "days_active": 65},
        {"id": "job_3", "title": "Product Manager", "days_active": 100},
    ]
    
    result = await detect_ghost_jobs(jobs)
    
    assert len(result) == 2
    ghost_ids = [job["id"] for job in result]
    assert "job_2" in ghost_ids
    assert "job_3" in ghost_ids
    assert "job_1" not in ghost_ids
    assert result[0]["ghost_score"] > 0
    assert "65 days ago" in result[0]["reason"]
