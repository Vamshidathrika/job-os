"""HTTP clients for the people-search providers used to find referrers.

Apollo supplies the candidate people at a target company; Icypeas is used to
find or verify a work email when Apollo does not expose one.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

APOLLO_SEARCH_URL = "https://api.apollo.io/v1/mixed_people/search"
ICYPEAS_EMAIL_SEARCH_URL = "https://app.icypeas.com/api/email-search"

REQUEST_TIMEOUT_SECONDS = 20.0

# Titles most likely to be able to actually submit a referral.
DEFAULT_TARGET_TITLES = [
    "engineering manager",
    "senior software engineer",
    "staff software engineer",
    "software engineer",
    "technical recruiter",
    "talent acquisition",
]


class ApolloClient:
    """Minimal Apollo people-search client."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("Apollo API key is required")
        self.api_key = api_key

    async def search_people(
        self,
        company_domain: str,
        titles: list[str] | None = None,
        per_page: int = 10,
    ) -> list[dict[str, Any]]:
        """Search people at a company domain.

        Returns an empty list on provider failure — a referral search that
        cannot reach Apollo must degrade to "no candidates", never raise into
        the warm-path race and abort the whole job.
        """
        payload = {
            "api_key": self.api_key,
            "q_organization_domains": company_domain,
            "person_titles": titles or DEFAULT_TARGET_TITLES,
            "page": 1,
            "per_page": per_page,
        }
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    APOLLO_SEARCH_URL,
                    json=payload,
                    headers={"Content-Type": "application/json", "Cache-Control": "no-cache"},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error("apollo_search_failed", company_domain=company_domain, error=str(e))
            return []

        people = data.get("people") or []
        logger.info("apollo_search_ok", company_domain=company_domain, count=len(people))
        return [p for p in people if isinstance(p, dict)]


class IcypeasClient:
    """Minimal Icypeas email-discovery client."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("Icypeas API key is required")
        self.api_key = api_key

    async def find_email(self, first_name: str, last_name: str, domain: str) -> str | None:
        """Look up a work email. Returns None when not found or on failure."""
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    ICYPEAS_EMAIL_SEARCH_URL,
                    json={
                        "firstname": first_name,
                        "lastname": last_name,
                        "domainOrCompany": domain,
                    },
                    headers={"Authorization": self.api_key, "Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error("icypeas_lookup_failed", domain=domain, error=str(e))
            return None

        # Icypeas nests the result under a few shapes depending on plan/route.
        for key in ("email", "result", "data"):
            value = data.get(key)
            if isinstance(value, str) and "@" in value:
                return value
            if isinstance(value, dict):
                nested = value.get("email")
                if isinstance(nested, str) and "@" in nested:
                    return nested
        return None
