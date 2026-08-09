"""Unit tests for job description normalizer."""

import pytest
from jobos.ingestion.normalizer import normalize_job


def test_normalize_job_greenhouse() -> None:
    raw_job = {
        "external_id": "gh-1",
        "title": "Software Engineer II",
        "location": "Remote",
        "description": "<p>Description</p>",
    }
    normalized = normalize_job(
        ats_type="greenhouse",
        raw_job=raw_job,
        company_id="comp-123",
        company_domain="acme.com",
    )
    assert normalized["external_id"] == "gh-1"
    assert normalized["title"] == "Software Engineer Ii" or normalized["title"] == "Software Engineer II"
    assert normalized["company_id"] == "comp-123"
    assert normalized["ats_type"] == "greenhouse"


@pytest.mark.parametrize("location_str", [
    "Hyderabad",
    "Bangalore",
    "India",
    "Bengaluru, India",
])
def test_normalize_job_country_detection_india(location_str: str) -> None:
    raw_job = {
        "external_id": "job-2",
        "title": "DevOps Engineer",
        "location": location_str,
        "description": "Some description",
    }
    normalized = normalize_job(
        ats_type="lever",
        raw_job=raw_job,
        company_id="comp-456",
        company_domain="swiggy.com",
    )
    assert normalized["country"] == "IN"


def test_normalize_job_html_stripping() -> None:
    raw_job = {
        "external_id": "job-3",
        "title": "Frontend Developer",
        "location": "US",
        "description": "<div><h2>Job details</h2><p>Here is a description.</p><ul><li>Skill A</li></ul></div>",
    }
    normalized = normalize_job(
        ats_type="ashby",
        raw_job=raw_job,
        company_id="comp-789",
        company_domain="zepto.com",
    )
    assert "<div>" not in normalized["description"]
    assert "<p>" not in normalized["description"]
    assert "Job details" in normalized["description"]
