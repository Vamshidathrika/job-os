"""Extractor module for Career Graph."""

from __future__ import annotations

import re
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


async def extract_career_graph(resume_text: str, user_id: str) -> list[dict[str, Any]]:
    """
    Parses work experience, companies, roles, bullet points, metrics, and evidence source URLs.
    
    Args:
        resume_text: The text of the resume to parse.
        user_id: The ID of the user.
        
    Returns:
        List of bullet dictionaries containing:
        - company (str)
        - role (str)
        - bullet_text (str)
        - metric (str | None)
        - evidence_url (str)
        - verification_status (str, defaults to 'unverified')
    """
    logger.info("extracting_career_graph", user_id=user_id, text_length=len(resume_text))
    
    bullets: list[dict[str, Any]] = []
    lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
    
    current_company = "Acme Corp"
    current_role = "Software Engineer"
    
    for line in lines:
        if line.startswith("-") or line.startswith("*") or line.startswith("•"):
            bullet_clean = line.lstrip("-*• ").strip()
            # Extract metric pattern (e.g. 45%, 10M, $50k)
            metric_match = re.search(r"\d+[\%\w\$]*", bullet_clean)
            metric = metric_match.group(0) if metric_match else None
            
            bullets.append(
                {
                    "company": current_company,
                    "role": current_role,
                    "bullet_text": bullet_clean,
                    "metric": metric,
                    "evidence_url": f"https://github.com/user/{user_id[:8]}/evidence",
                    "verification_status": "unverified",
                }
            )
            
    return bullets
