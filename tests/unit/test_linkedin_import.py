"""Tests for parsing a LinkedIn data export."""

import csv
import io
import zipfile

import pytest

from jobos.onboarding.linkedin_import import (
    LinkedInExportError,
    parse_linkedin_export,
)

POSITIONS = [
    ["Company Name", "Title", "Description", "Location", "Started On", "Finished On"],
    ["Acme", "Backend Engineer", "Built a Redis cache cutting p99 45%", "Bengaluru", "Jan 2022", "Mar 2024"],
]
EDUCATION = [
    ["School Name", "Start Date", "End Date", "Degree Name"],
    ["IIT Madras", "2016", "2020", "B.Tech"],
]
SKILLS = [["Name"], ["Python"], ["PostgreSQL"]]
# LinkedIn prefixes Connections.csv with a notes preamble before the header.
CONNECTIONS_PREAMBLE = "Notes:\nWhen exporting your connections...\n\n"
CONNECTIONS = [
    ["First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"],
    ["Ravi", "Kumar", "https://linkedin.com/in/ravi", "", "Globex", "Engineering Manager", "01 Feb 2024"],
]


def _csv(rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


@pytest.fixture
def export_zip(tmp_path):
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Positions.csv", _csv(POSITIONS))
        archive.writestr("Education.csv", _csv(EDUCATION))
        archive.writestr("Skills.csv", _csv(SKILLS))
        archive.writestr("Connections.csv", CONNECTIONS_PREAMBLE + _csv(CONNECTIONS))
    return str(path)


def test_parses_positions(export_zip):
    profile = parse_linkedin_export(export_zip)

    assert len(profile.positions) == 1
    assert profile.positions[0]["company"] == "Acme"
    assert profile.positions[0]["title"] == "Backend Engineer"


def test_parses_skills_and_education(export_zip):
    profile = parse_linkedin_export(export_zip)

    assert profile.skills == ["Python", "PostgreSQL"]
    assert profile.education[0]["institution"] == "IIT Madras"


def test_skips_the_connections_preamble(export_zip):
    """Connections.csv starts with a notes block before the real header."""
    profile = parse_linkedin_export(export_zip)

    assert len(profile.connections) == 1
    assert profile.connections[0]["name"] == "Ravi Kumar"
    assert profile.connections[0]["company"] == "Globex"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_linkedin_export(str(tmp_path / "nope.zip"))


def test_archive_without_any_expected_csv_raises(tmp_path):
    """A wrong ZIP must fail loudly rather than import an empty profile."""
    path = tmp_path / "wrong.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("holiday-photo.jpg", "not a csv")

    with pytest.raises(LinkedInExportError):
        parse_linkedin_export(str(path))


def test_unexpected_headers_fail_loudly(tmp_path):
    """LinkedIn changing its column names must not silently yield nothing."""
    path = tmp_path / "renamed.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Positions.csv", _csv([["Org", "Job"], ["Acme", "Engineer"]]))

    with pytest.raises(LinkedInExportError, match="Positions.csv"):
        parse_linkedin_export(str(path))
