"""Referral candidate finder."""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)

async def find_referrers(company_domain: str, user_profile: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Searches Apollo + Icypeas for people at target company.
    Returns list of referrer candidates with name, title, email, shared_school, shared_past_company, linkedin_url.
    """
    logger.info("Finding referrers", company_domain=company_domain)
    # TODO: Integrate Apollo + Icypeas
    return []
