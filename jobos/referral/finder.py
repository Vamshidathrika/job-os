"""Referral candidate finder."""

from __future__ import annotations

from typing import Any

import structlog

from jobos.referral.providers import ApolloClient, IcypeasClient

logger = structlog.get_logger(__name__)


async def find_referrers(
    company_domain: str,
    user_profile: dict[str, Any],
    apollo: ApolloClient,
    icypeas: IcypeasClient | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Searches candidate databases (Apollo / Icypeas) for potential referrers at target company.
    Returns list of referrer candidates with name, title, email, shared_school, shared_past_company, linkedin_url.

    Every field is sourced from the provider response. Nothing is synthesised:
    a guessed address like referral@<domain> would send real outreach to an
    address that does not exist and burn the sending domain's reputation.
    Candidates are ranked by genuine overlap with the user so the sequence
    generator spends its budget on the warmest paths first.
    """
    logger.info("finding_referrers", company_domain=company_domain)

    people = await apollo.search_people(company_domain=company_domain, per_page=limit)
    if not people:
        logger.info("no_referrers_found", company_domain=company_domain)
        return []

    user_schools = _normalized_set(user_profile.get("schools"))
    user_past_cos = _normalized_set(user_profile.get("past_companies"))

    candidates: list[dict[str, Any]] = []
    for person in people:
        first_name = str(person.get("first_name") or "").strip()
        last_name = str(person.get("last_name") or "").strip()
        full_name = " ".join(part for part in (first_name, last_name) if part)
        if not full_name:
            continue

        shared_school = sorted(user_schools & _normalized_set(_extract_schools(person)))
        shared_past_company = sorted(user_past_cos & _normalized_set(_extract_past_companies(person)))

        email = person.get("email")
        if not _is_usable_email(email) and icypeas and first_name and last_name:
            # Apollo often withholds the address behind a paid unlock; fall
            # back to Icypeas rather than dropping an otherwise warm lead.
            email = await icypeas.find_email(first_name, last_name, company_domain)

        candidates.append(
            {
                "name": full_name,
                "title": person.get("title"),
                "email": email if _is_usable_email(email) else None,
                "email_verified": _is_usable_email(email),
                "linkedin_url": person.get("linkedin_url"),
                "company_domain": company_domain,
                "shared_school": shared_school,
                "shared_past_company": shared_past_company,
                "warmth_score": _warmth_score(shared_school, shared_past_company, email),
            }
        )

    candidates.sort(key=lambda c: c["warmth_score"], reverse=True)
    logger.info(
        "referrers_discovered",
        company_domain=company_domain,
        count=len(candidates),
        with_email=sum(1 for c in candidates if c["email"]),
    )
    return candidates


def _warmth_score(shared_school: list[str], shared_past_company: list[str], email: Any) -> float:
    """Score a candidate by real, checkable overlap with the user.

    A shared employer outranks a shared school: former colleagues reply more
    often than alumni. Reachability counts too — a perfect match with no
    address cannot be contacted at all.
    """
    score = 0.0
    if shared_past_company:
        score += 0.5
    if shared_school:
        score += 0.3
    if _is_usable_email(email):
        score += 0.2
    return round(score, 2)


def _is_usable_email(email: Any) -> bool:
    """Whether an address is real rather than a provider placeholder."""
    if not isinstance(email, str) or "@" not in email:
        return False
    return "email_not_unlocked" not in email and not email.startswith("noreply@")


def _extract_schools(person: dict[str, Any]) -> list[str]:
    """Pull school names out of an Apollo person record."""
    schools: list[str] = []
    for entry in person.get("employment_history") or []:
        if (
            isinstance(entry, dict)
            and entry.get("kind") == "education"
            and entry.get("organization_name")
        ):
            schools.append(str(entry["organization_name"]))
    for key in ("school", "schools"):
        value = person.get(key)
        if isinstance(value, str):
            schools.append(value)
        elif isinstance(value, list):
            schools.extend(str(v) for v in value if v)
    return schools


def _extract_past_companies(person: dict[str, Any]) -> list[str]:
    """Pull previous employer names out of an Apollo person record."""
    companies: list[str] = []
    for entry in person.get("employment_history") or []:
        if not isinstance(entry, dict) or entry.get("kind") == "education":
            continue
        name = entry.get("organization_name")
        # Only *past* employers count as shared history worth citing.
        if name and not entry.get("current"):
            companies.append(str(name))
    return companies


def _normalized_set(values: Any) -> set[str]:
    """Lowercase/strip a name list for tolerant comparison."""
    if not values:
        return set()
    if isinstance(values, str):
        values = [values]
    return {str(v).strip().lower() for v in values if str(v).strip()}
