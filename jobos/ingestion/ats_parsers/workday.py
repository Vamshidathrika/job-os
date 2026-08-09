"""Workday ATS parser."""

from __future__ import annotations

from typing import Any


def parse_workday_jobs(data: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse Workday jobs from API response."""
    jobs: list[Any] = []
    if isinstance(data, dict):
        jobs = data.get("jobPostings", [])
    elif isinstance(data, list):
        jobs = data
    
    parsed: list[dict[str, Any]] = []
    for job in jobs:
        if isinstance(job, dict):
            parsed.append(
                {
                    "external_id": str(job.get("bulletin") or job.get("jobId") or ""),
                    "title": str(job.get("title") or ""),
                    "location": str(job.get("locationsText") or ""),
                    "description": str(job.get("jobPostingDescription") or ""),
                }
            )
    return parsed
