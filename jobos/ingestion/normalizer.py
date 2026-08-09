"""Job normalizer."""

from __future__ import annotations

import re
from typing import Any


def clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    clean = re.compile("<.*?>")
    return re.sub(clean, " ", text).strip()


def normalize_job(
    ats_type: str, raw_job: dict[str, Any], company_id: str, company_domain: str
) -> dict[str, Any]:
    """Normalize a raw job dict to a standard schema."""
    title = str(raw_job.get("title") or "").strip().title()
    location = str(raw_job.get("location") or "").strip()
    
    loc_lower = location.lower()
    india_keywords = ["india", "hyderabad", "bangalore", "bengaluru", "pune", "mumbai", "chennai", "delhi", "gurgaon", "noida"]
    
    if any(k in loc_lower for k in india_keywords):
        country = "IN"
    else:
        country = "US" if not location else "US" # Fallback to US, real implementation might use NLP
        
    description_raw = raw_job.get("content") or raw_job.get("description") or raw_job.get("descriptionPlain") or raw_job.get("descriptionHtml") or ""
    description = clean_html(str(description_raw))

    return {
        "company_id": company_id,
        "external_id": raw_job.get("external_id") or "unknown",
        "title": title,
        "location": location,
        "country": country,
        "description": description,
        "raw_json": raw_job,
        "ats_type": ats_type,
    }
