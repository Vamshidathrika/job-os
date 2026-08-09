import pytest
from datetime import datetime, timezone

from jobos.content.generator import generate_engagement_post
from jobos.content.comment_engine import generate_smart_comment
from jobos.content.scheduler import ContentScheduler

@pytest.mark.asyncio
async def test_generate_engagement_post_linkedin():
    """Test LinkedIn post generation returns content + hashtags."""
    topic = "AI in Recruitment"
    user_profile = {"title": "Software Engineer"}
    
    result = await generate_engagement_post(topic, user_profile, platform="linkedin")
    
    assert "content" in result
    assert "hashtags" in result
    assert isinstance(result["content"], str)
    assert isinstance(result["hashtags"], list)
    assert len(result["hashtags"]) > 0

def test_generate_smart_comment():
    """Test comment is non-empty and relevant."""
    post_content = "We are releasing our new ATS platform today."
    user_expertise = ["Python", "System Design"]
    target_company = "TechCorp"
    
    comment = generate_smart_comment(post_content, user_expertise, target_company)
    
    assert isinstance(comment, str)
    assert len(comment) > 0
    assert target_company in comment
    assert "Python" in comment or "System Design" in comment

def test_content_scheduler_optimal_time():
    """Test optimal time returns valid datetime."""
    scheduler = ContentScheduler(tenant_id="tenant-123")
    optimal_time = scheduler.get_optimal_time(platform="linkedin", timezone="UTC")
    
    assert isinstance(optimal_time, datetime)
    assert optimal_time > datetime.utcnow()
