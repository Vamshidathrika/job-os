import pytest

from jobos.profile.optimizer import analyze_profile
from jobos.profile.keyword_extractor import extract_target_keywords

@pytest.mark.asyncio
async def test_analyze_profile_returns_score():
    """Test profile analysis returns 0-100 score."""
    profile_data = {
        "headline": "Software Engineer",
        "summary": "Building scalable systems.",
        "experience": []
    }
    
    result = await analyze_profile(profile_data)
    
    assert "score" in result
    assert isinstance(result["score"], (int, float))
    assert 0 <= result["score"] <= 100
    assert "suggestions" in result
    assert isinstance(result["suggestions"], list)

def test_extract_target_keywords():
    """Test keyword extraction from job descriptions."""
    job_descriptions = [
        "Looking for a Python developer with AWS experience.",
        "Need someone strong in FastAPI and system design."
    ]
    
    keywords = extract_target_keywords(job_descriptions)
    
    assert isinstance(keywords, dict)
    assert len(keywords) > 0
    assert "python" in keywords
    assert "aws" in keywords
    for score in keywords.values():
        assert isinstance(score, float)
