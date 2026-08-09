"""Unit tests for Resume Tailorer and Parse Fidelity."""

import pytest
from jobos.config import settings
from jobos.tailorer import generate_tailored_resume, evaluate_parse_fidelity


@pytest.mark.asyncio
async def test_generate_tailored_resume() -> None:
    jd = "Seeking Senior Backend Engineer proficient in Python, FastAPI, and PostgreSQL."
    bullets = [
        {"id": "b1", "bullet_text": "Built FastAPI backend serving 50k DAU."},
        {"id": "b2", "bullet_text": "Optimized PostgreSQL queries reducing P99 latency by 30%."},
    ]
    result = await generate_tailored_resume(jd, bullets, settings=settings)
    assert "tailored_text" in result
    assert "used_bullet_ids" in result


def test_ats_parse_fidelity() -> None:
    original = "Senior Software Engineer with 5 years experience in Python and AWS."
    tailored = "Senior Software Engineer with 5 years experience in Python, AWS, and FastAPI."
    score = evaluate_parse_fidelity(original, tailored)
    assert 0.0 <= score <= 1.0
