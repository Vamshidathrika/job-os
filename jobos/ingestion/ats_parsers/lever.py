"""Lever ATS parser."""

from __future__ import annotations

from typing import Any


def parse_lever_jobs(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse Lever jobs from API response."""
    parsed = []
    for job in data:
        categories = job.get("categories", {})
        parsed.append(
            {
                "external_id": str(job.get("id")),
                "title": job.get("text"),
                "location": categories.get("location") or categories.get("country"),
                "description": job.get("descriptionPlain") or job.get("description"),
                "categories": {
                    "team": categories.get("team"),
                    "department": categories.get("department"),
                    "commitment": categories.get("commitment"),
                },
            }
        )
    return parsed
