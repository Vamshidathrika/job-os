"""GDPR and DPDP compliance helpers."""

from __future__ import annotations

import hashlib
import structlog

logger = structlog.get_logger(__name__)


def gdpr_art14_footer(tenant_name: str, company: str, data_source: str) -> str:
    """Generates the GDPR Article 14 disclosure footer."""
    return (
        f"You are receiving this message from {tenant_name} on behalf of {company}. "
        f"Your contact information was sourced from {data_source}."
    )


def dpdp_notice(tenant_name: str) -> str:
    """Generates DPDP Act notice."""
    return (
        f"{tenant_name} is processing this data in accordance with the DPDP Act. "
        "You have the right to request deletion of your data at any time."
    )


def hash_email_for_suppression(email: str) -> str:
    """Returns the SHA-256 hash of the lowercased email for suppression lists."""
    return hashlib.sha256(email.strip().lower().encode('utf-8')).hexdigest()
