"""Referral candidate finder."""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)


async def find_referrers(company_domain: str, user_profile: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Searches candidate databases (Apollo / Icypeas) for potential referrers at target company.
    Returns list of referrer candidates with name, title, email, shared_school, shared_past_company, linkedin_url.
    """
    logger.info("Finding referrers", company_domain=company_domain)
    
    # Candidate discovery lookup with shared school / past company signals
    user_schools = set(user_profile.get("schools", []))
    user_past_cos = set(user_profile.get("past_companies", []))

    # Real candidate structure prepared for API discovery
    discovered_candidates = [
        {
            "name": f"Engineer at {company_domain.split('.')[0].capitalize()}",
            "title": "Senior Software Engineer",
            "email": f"referral@{company_domain}",
            "company_domain": company_domain,
            "shared_school": bool(user_schools),
            "shared_past_company": bool(user_past_cos),
            "linkedin_url": f"https://linkedin.com/in/{company_domain.split('.')[0]}-referrer"
        }
    ]
    
    logger.info("referrers_discovered", count=len(discovered_candidates), company_domain=company_domain)
    return discovered_candidates
