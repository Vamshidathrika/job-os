"""Greenhouse ATS parser."""

from __future__ import annotations

from typing import Any


def parse_greenhouse_jobs(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Greenhouse jobs from API response."""
    jobs = data.get("jobs", [])
    parsed = []
    for job in jobs:
        parsed.append(
            {
                "external_id": str(job.get("id")),
                "title": job.get("title"),
                "location": job.get("location", {}).get("name"),
                "updated_at": job.get("updated_at"),
                "content": job.get("content") or job.get("description"),
                "departments": [d.get("name") for d in job.get("departments", []) if isinstance(d, dict)],
                "offices": [o.get("name") for o in job.get("offices", []) if isinstance(o, dict)],
            }
        )
    return parsed
