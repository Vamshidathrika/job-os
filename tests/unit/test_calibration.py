import pytest
from jobos.calibration.ghost_tracker import detect_ghost_jobs


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
