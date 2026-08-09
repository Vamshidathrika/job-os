"""Unit tests for ATS parsers (Greenhouse, Lever, Ashby, Workday)."""

from typing import Any, Dict
import pytest

from jobos.ingestion.ats_parsers import (
    parse_greenhouse_jobs,
    parse_lever_jobs,
    parse_ashby_jobs,
    parse_workday_jobs,
)


@pytest.fixture
def greenhouse_payload() -> Dict[str, Any]:
    return {
        "jobs": [
            {
                "id": 12345,
                "title": "Software Engineer",
                "location": {"name": "Hyderabad, India"},
                "updated_at": "2026-08-01T10:00:00Z",
                "content": "<p>We are hiring a Software Engineer</p>",
            }
        ]
    }


@pytest.fixture
def lever_payload() -> list[Dict[str, Any]]:
    return [
        {
            "id": "lev-67890",
            "text": "Data Scientist",
            "categories": {
                "location": "Bangalore, India",
                "team": "Data Science",
            },
            "description": "Build ML models",
            "descriptionPlain": "Build ML models",
        }
    ]


@pytest.fixture
def ashby_payload() -> Dict[str, Any]:
    return {
        "jobs": [
            {
                "id": "as-54321",
                "title": "Product Manager",
                "location": "San Francisco, CA",
                "descriptionHtml": "<h2>Role</h2><p>Great PM role</p>",
                "descriptionPlain": "Great PM role",
            }
        ]
    }


@pytest.fixture
def workday_payload() -> Dict[str, Any]:
    return {
        "jobPostings": [
            {
                "bulletin": "wd-98765",
                "jobId": "wd-98765",
                "title": "HR Specialist",
                "locationsText": "London, UK",
                "jobPostingDescription": "Manage HR things.",
            }
        ]
    }


def test_parse_greenhouse_jobs(greenhouse_payload: Dict[str, Any]) -> None:
    jobs = parse_greenhouse_jobs(greenhouse_payload)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["external_id"] == "12345"
    assert job["title"] == "Software Engineer"
    assert "Hyderabad" in job["location"]


def test_parse_lever_jobs(lever_payload: list[Dict[str, Any]]) -> None:
    jobs = parse_lever_jobs(lever_payload)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["external_id"] == "lev-67890"
    assert job["title"] == "Data Scientist"


def test_parse_ashby_jobs(ashby_payload: Dict[str, Any]) -> None:
    jobs = parse_ashby_jobs(ashby_payload)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["external_id"] == "as-54321"
    assert job["title"] == "Product Manager"


def test_parse_workday_jobs(workday_payload: Dict[str, Any]) -> None:
    jobs = parse_workday_jobs(workday_payload)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["external_id"] == "wd-98765"
    assert job["title"] == "HR Specialist"
