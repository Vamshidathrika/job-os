"""Existing network graph mapper."""

from __future__ import annotations

from typing import Any
import structlog
from jobos.utils.text_matching import compute_fuzzy_similarity

logger = structlog.get_logger(__name__)


async def map_existing_network(user_contacts: list[dict[str, Any]], target_companies: list[str]) -> list[dict[str, Any]]:
    """
    Maps user's existing contacts to target companies BEFORE doing cold referral search.
    Returns warm leads from existing network matching target companies.
    """
    logger.info("Mapping existing network", total_contacts=len(user_contacts), target_companies=len(target_companies))
    
    warm_leads: list[dict[str, Any]] = []
    
    for contact in user_contacts:
        contact_company = contact.get("company", "")
        if not contact_company:
            continue
            
        for target in target_companies:
            score = compute_fuzzy_similarity(contact_company, target)
            if score >= 0.5:
                warm_lead = dict(contact)
                warm_lead["matched_target_company"] = target
                warm_lead["match_score"] = score
                warm_leads.append(warm_lead)
                break
                
    logger.info("network_mapping_complete", warm_leads_found=len(warm_leads))
    return warm_leads
