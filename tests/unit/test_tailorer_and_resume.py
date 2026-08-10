"""Unit tests for resume tailoring and resume parsing."""

import json

import pytest

from jobos.config import Settings
from jobos.onboarding.resume_parser import (
    UnsupportedResumeFormatError,
    extract_text,
    parse_uploaded_resume,
)
from jobos.tailorer.generator import generate_tailored_resume

BULLETS = [
    {"id": "b1", "bullet_text": "Cut checkout latency 40% by adding a Redis cache", "company": "Freshworks"},
    {"id": "b2", "bullet_text": "Led migration of 12 services to Kubernetes", "company": "Freshworks"},
]


def _llm_reply(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


async def test_tailoring_returns_selected_bullets(mocker):
    mocker.patch(
        "jobos.tailorer.generator.acompletion",
        return_value=_llm_reply(
            {"used_bullet_ids": ["b1"], "tailored_text": "Cut checkout latency 40% with Redis"}
        ),
    )

    result = await generate_tailored_resume("Backend role, latency focus", BULLETS, Settings())

    assert result["used_bullet_ids"] == ["b1"]
    assert "latency" in result["tailored_text"]
    # The old implementation returned this literal regardless of input.
    assert result["tailored_text"] != "Tailored resume content placeholder."


async def test_tailoring_rejects_bullets_that_were_never_supplied(mocker):
    """Citing an unknown bullet is fabricated provenance — refuse the output."""
    mocker.patch(
        "jobos.tailorer.generator.acompletion",
        return_value=_llm_reply(
            {"used_bullet_ids": ["b1", "b99"], "tailored_text": "Invented achievement"}
        ),
    )

    result = await generate_tailored_resume("Backend role", BULLETS, Settings())

    assert result == {"tailored_text": "", "used_bullet_ids": []}


async def test_tailoring_without_verified_bullets_returns_empty(mocker):
    llm = mocker.patch("jobos.tailorer.generator.acompletion")

    result = await generate_tailored_resume("Backend role", [], Settings())

    assert result == {"tailored_text": "", "used_bullet_ids": []}
    llm.assert_not_called(), "must not spend a call when nothing is verified"


async def test_tailoring_survives_model_failure(mocker):
    mocker.patch(
        "jobos.tailorer.generator.acompletion", side_effect=RuntimeError("provider down")
    )

    result = await generate_tailored_resume("Backend role", BULLETS, Settings())

    assert result == {"tailored_text": "", "used_bullet_ids": []}


async def test_tailoring_rejects_unparseable_output(mocker):
    mocker.patch(
        "jobos.tailorer.generator.acompletion",
        return_value={"choices": [{"message": {"content": "sorry, I can't do that"}}]},
    )

    result = await generate_tailored_resume("Backend role", BULLETS, Settings())

    assert result == {"tailored_text": "", "used_bullet_ids": []}


def test_extract_text_reads_a_real_file(tmp_path):
    resume = tmp_path / "cv.txt"
    resume.write_text("Asha Rao\nasha@example.com\n+91 98765 43210\n")

    assert "Asha Rao" in extract_text(str(resume))


def test_extract_text_rejects_unsupported_format(tmp_path):
    bad = tmp_path / "cv.rtf"
    bad.write_text("x")

    with pytest.raises(UnsupportedResumeFormatError):
        extract_text(str(bad))


def test_extract_text_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        extract_text("/nonexistent/cv.pdf")


async def test_parse_resume_uses_real_file_contents(tmp_path, mocker):
    resume = tmp_path / "cv.txt"
    resume.write_text("Asha Rao\nasha@example.com\n+91 98765 43210\nEngineer at Freshworks\n")

    mocker.patch(
        "jobos.onboarding.resume_parser.acompletion",
        return_value=_llm_reply(
            {
                "name": "Asha Rao",
                "email": "asha@example.com",
                "phone": "+91 98765 43210",
                "education": [],
                "experience": [{"company": "Freshworks", "title": "Engineer"}],
                "skills": ["python"],
                "summary": "Engineer",
            }
        ),
    )

    parsed = await parse_uploaded_resume(str(resume))

    assert parsed["name"] == "Asha Rao"
    assert parsed["experience"][0]["company"] == "Freshworks"
    # The old implementation always returned this fixture regardless of input.
    assert parsed["name"] != "Jane Doe"
    assert parsed["email"] != "jane.doe@example.com"


async def test_parse_resume_recovers_contacts_when_model_fails(tmp_path, mocker):
    """A model outage must not lose facts we can read straight from the text."""
    resume = tmp_path / "cv.txt"
    resume.write_text("Asha Rao\nasha@example.com\n+91 98765 43210\n")

    mocker.patch(
        "jobos.onboarding.resume_parser.acompletion", side_effect=RuntimeError("down")
    )

    parsed = await parse_uploaded_resume(str(resume))

    assert parsed["email"] == "asha@example.com"
    assert parsed["name"] == ""  # not invented
    assert parsed["experience"] == []


async def test_parse_empty_resume_returns_empty_schema(tmp_path, mocker):
    resume = tmp_path / "cv.txt"
    resume.write_text("   \n  ")
    llm = mocker.patch("jobos.onboarding.resume_parser.acompletion")

    parsed = await parse_uploaded_resume(str(resume))

    assert parsed["name"] == ""
    llm.assert_not_called()
