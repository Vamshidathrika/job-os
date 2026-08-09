"""Ashby ATS parser."""

from __future__ import annotations

from typing import Any


def parse_ashby_jobs(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Ashby jobs from API response."""
    jobs = data.get("jobs", [])
    parsed = []
    for job in jobs:
        parsed.append(
            {
                "external_id": str(job.get("id")),
                "title": job.get("title"),
                "location": job.get("locationName"),
                "descriptionHtml": job.get("descriptionHtml"),
                "descriptionPlain": job.get("descriptionPlain"),
                "employmentType": job.get("employmentType"),
                "departmentName": job.get("departmentName"),
            }
        )
    return parsed
