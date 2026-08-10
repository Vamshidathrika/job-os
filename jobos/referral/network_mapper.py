"""Existing network graph mapper."""

from __future__ import annotations

import re
from typing import Any

import structlog

from jobos.utils.text_matching import compute_fuzzy_similarity, normalize_text

logger = structlog.get_logger(__name__)

FUZZY_MATCH_THRESHOLD = 0.5

# Legal/marketing suffixes carry no identifying information but wreck token
# overlap scoring: "Acme Technologies Pvt Ltd" vs "Acme" is only 0.25 Jaccard,
# well under threshold, even though they are obviously the same employer.
_COMPANY_NOISE = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|co|company|gmbh|pvt|private|plc"
    r"|technologies|technology|labs|software|solutions|systems|services"
    r"|group|holdings|india)\b",
    re.IGNORECASE,
)


async def map_existing_network(
    user_contacts: list[dict[str, Any]], target_companies: list[str]
) -> list[dict[str, Any]]:
    """
    Maps user's existing contacts to target companies BEFORE doing cold referral search.
    Returns warm leads from existing network matching target companies.

    An existing contact beats any purchased record, so this runs first and its
    results should be exhausted before paying for cold people-search.
    """
    logger.info(
        "Mapping existing network",
        total_contacts=len(user_contacts),
        target_companies=len(target_companies),
    )

    targets = [(target, _core_name(target)) for target in target_companies]
    warm_leads: list[dict[str, Any]] = []

    for contact in user_contacts:
        contact_company = contact.get("company") or contact.get("company_domain") or ""
        if not contact_company:
            continue

        contact_core = _core_name(contact_company)
        if not contact_core:
            continue

        for target, target_core in targets:
            score = _similarity(contact_core, target_core)
            if score >= FUZZY_MATCH_THRESHOLD:
                warm_lead = dict(contact)
                warm_lead["matched_target_company"] = target
                warm_lead["match_score"] = score
                warm_lead["source"] = "existing_network"
                warm_leads.append(warm_lead)
                break

    logger.info("network_mapping_complete", warm_leads_found=len(warm_leads))
    return warm_leads


def _similarity(contact_core: str, target_core: str) -> float:
    """Compare two already-normalized company names."""
    if not contact_core or not target_core:
        return 0.0
    if contact_core == target_core:
        return 1.0
    return compute_fuzzy_similarity(contact_core, target_core)


def _core_name(value: Any) -> str:
    """Reduce a company name or domain to its identifying core.

    "Acme Technologies Pvt Ltd", "acme.com" and "Acme" all reduce to "acme".
    """
    text = str(value or "").strip().lower()
    if not text:
        return ""

    # Domain form: keep the registrable label, drop scheme/path/TLD.
    if "." in text and " " not in text:
        label = text.split("//")[-1].split("/")[0].split(".")[0]
        if label and label != "www":
            return label

    return normalize_text(_COMPANY_NOISE.sub(" ", text))
