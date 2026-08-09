"""Unit tests for Career Graph Evidence Engine."""

import pytest
from jobos.career_graph import extract_career_graph


@pytest.mark.asyncio
async def test_extract_career_graph() -> None:
    resume_text = """
    Software Engineer at Acme Corp (2022 - Present)
    - Scaled microservices architecture processing 10M requests/day with 99.99% uptime.
    - Reduced database query latency by 45% using Redis caching.
    """
    bullets = await extract_career_graph(resume_text, user_id="550e8400-e29b-41d4-a716-446655440000")
    assert len(bullets) >= 1
    b = bullets[0]
    assert "company" in b
    assert "role" in b
    assert "bullet_text" in b
    assert b["verification_status"] == "unverified"
