"""Keyword extraction from job descriptions."""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

def extract_target_keywords(job_descriptions: list[str]) -> dict[str, float]:
    """
    Extract and score target keywords from a list of job descriptions.

    WHAT: Parses text to find frequently occurring hard skills, tools, and domain terms.
    WHY: To identify keyword gaps in the user's profile so they can optimize for ATS and recruiters.
    """
    logger.info("extracting_keywords", num_descriptions=len(job_descriptions))
    
    # Placeholder extraction logic
    return {
        "python": 0.95,
        "fastapi": 0.85,
        "aws": 0.80,
        "system design": 0.75,
    }
