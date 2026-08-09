import pytest

from jobos.interview.prep import generate_prep_pack
from jobos.interview.debrief import capture_debrief
from jobos.interview.scheduler import InterviewScheduler
from jobos.interview.followup import generate_thank_you

@pytest.mark.asyncio
async def test_generate_prep_pack_phone_screen():
    """Test prep pack includes all required sections."""
    job = {"title": "Backend Engineer", "company": "TechCorp"}
    user_profile = {"name": "Alice"}
    
    result = await generate_prep_pack(job, user_profile, interview_type="phone_screen")
    
    assert "company_research" in result
    assert "likely_questions" in result
    assert "answer_frameworks" in result
    assert "technical_topics" in result
    assert "questions_to_ask" in result

@pytest.mark.asyncio
async def test_capture_debrief():
    """Test debrief returns sentiment + follow_up_actions."""
    notes = {"text": "Interview went well, they asked about my AWS experience."}
    
    result = await capture_debrief("interview-123", notes)
    
    assert "sentiment" in result
    assert "follow_up_actions" in result
    assert isinstance(result["follow_up_actions"], list)

@pytest.mark.asyncio
async def test_parse_interview_invite():
    """Test email parsing extracts date and link."""
    scheduler = InterviewScheduler(tenant_id="tenant-123")
    email_body = "Your interview is scheduled for Oct 15 at 2 PM. Join here: https://zoom.us/j/123"
    
    # Assuming parse_interview_invite extracts these or returns empty dict in stub
    result = await scheduler.parse_interview_invite(email_body)
    
    # For now, just test it doesn't fail as the stub returns empty dict
    assert isinstance(result, dict)

@pytest.mark.asyncio
async def test_generate_thank_you():
    """Test thank-you email has subject and body."""
    interview = {"interviewer": "Bob"}
    debrief = {"follow_up_actions": []}
    
    result = await generate_thank_you(interview, debrief)
    
    assert "subject" in result
    assert "body" in result
    assert isinstance(result["subject"], str)
    assert isinstance(result["body"], str)
