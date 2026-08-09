import pytest
from jobos.followup.nudge import generate_status_nudge

@pytest.mark.asyncio
async def test_generate_status_nudge() -> None:
    """Test nudge has subject and body, tone is professional."""
    interview = {
        "id": "123",
        "company_name": "Tech Corp",
        "role_title": "Software Engineer"
    }
    
    result = await generate_status_nudge(interview, days_since=7)
    
    assert "subject" in result
    assert "body" in result
    assert "Tech Corp" in result["subject"]
    assert "Software Engineer" in result["subject"]
    assert "7 days since our interview" in result["body"]
    assert "very interested" in result["body"]
