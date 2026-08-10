"""Import a LinkedIn data export into the Career Graph.

LinkedIn's own export (Settings -> Data Privacy -> Get a copy of your data) is
the only legitimate source of a member's full profile: the official API scope
this project uses is post-only, and scraping violates LinkedIn's terms.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

POSITIONS_FILE = "Positions.csv"
EDUCATION_FILE = "Education.csv"
SKILLS_FILE = "Skills.csv"
CONNECTIONS_FILE = "Connections.csv"

# One required column per file, used to detect a changed export format.
REQUIRED_COLUMNS = {
    POSITIONS_FILE: "Company Name",
    EDUCATION_FILE: "School Name",
    SKILLS_FILE: "Name",
    CONNECTIONS_FILE: "First Name",
}


class LinkedInExportError(ValueError):
    """Raised when the archive is not a usable LinkedIn export."""


@dataclass
class LinkedInProfile:
    """Structured contents of a LinkedIn export."""

    positions: list[dict[str, Any]] = field(default_factory=list)
    education: list[dict[str, Any]] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    connections: list[dict[str, Any]] = field(default_factory=list)


def parse_linkedin_export(zip_path: str) -> LinkedInProfile:
    """Parse a LinkedIn export ZIP.

    Raises:
        FileNotFoundError: if the archive does not exist.
        LinkedInExportError: if it contains none of the expected files, or a
            file is present but its columns have changed.
    """
    path = Path(zip_path)
    if not path.exists():
        raise FileNotFoundError(f"LinkedIn export not found: {zip_path}")

    profile = LinkedInProfile()
    with zipfile.ZipFile(path) as archive:
        names = {Path(n).name: n for n in archive.namelist()}
        recognised = [f for f in REQUIRED_COLUMNS if f in names]
        if not recognised:
            raise LinkedInExportError(
                f"{zip_path} contains none of {sorted(REQUIRED_COLUMNS)} — "
                "is this a LinkedIn data export?"
            )

        for filename in recognised:
            rows = _read_csv(archive, names[filename], filename)
            if filename == POSITIONS_FILE:
                profile.positions = [_position(r) for r in rows]
            elif filename == EDUCATION_FILE:
                profile.education = [_education(r) for r in rows]
            elif filename == SKILLS_FILE:
                profile.skills = [r["Name"].strip() for r in rows if r.get("Name", "").strip()]
            elif filename == CONNECTIONS_FILE:
                profile.connections = [_connection(r) for r in rows]

    logger.info(
        "linkedin_export_parsed",
        positions=len(profile.positions),
        education=len(profile.education),
        skills=len(profile.skills),
        connections=len(profile.connections),
    )
    return profile


def _read_csv(archive: zipfile.ZipFile, member: str, filename: str) -> list[dict[str, str]]:
    """Read one CSV, skipping LinkedIn's notes preamble if present."""
    text = archive.read(member).decode("utf-8-sig", errors="replace")
    required = REQUIRED_COLUMNS[filename]

    # Connections.csv opens with a "Notes:" block before the real header.
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if required in line), None)
    if start is None:
        raise LinkedInExportError(
            f"{filename} has no {required!r} column — LinkedIn's export format may have changed"
        )

    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])))
    return [row for row in reader if any((v or "").strip() for v in row.values())]


def _position(row: dict[str, str]) -> dict[str, Any]:
    return {
        "company": (row.get("Company Name") or "").strip(),
        "title": (row.get("Title") or "").strip(),
        "description": (row.get("Description") or "").strip(),
        "location": (row.get("Location") or "").strip(),
        "started_on": (row.get("Started On") or "").strip(),
        "finished_on": (row.get("Finished On") or "").strip(),
    }


def _education(row: dict[str, str]) -> dict[str, Any]:
    return {
        "institution": (row.get("School Name") or "").strip(),
        "degree": (row.get("Degree Name") or "").strip(),
        "start": (row.get("Start Date") or "").strip(),
        "end": (row.get("End Date") or "").strip(),
    }


def _connection(row: dict[str, str]) -> dict[str, Any]:
    first = (row.get("First Name") or "").strip()
    last = (row.get("Last Name") or "").strip()
    return {
        "name": " ".join(p for p in (first, last) if p),
        "company": (row.get("Company") or "").strip(),
        "title": (row.get("Position") or "").strip(),
        "linkedin_url": (row.get("URL") or "").strip(),
        "email": (row.get("Email Address") or "").strip(),
    }


async def import_profile(
    conn: Any,
    user_id: str,
    zip_path: str | None = None,
    resume_path: str | None = None,
) -> dict[str, int]:
    """Merge a LinkedIn export and/or résumé into the Career Graph.

    Where the two disagree the LinkedIn export wins: it is structured data
    rather than text parsed out of a PDF.

    Bullets land as 'unverified' — imported history is claimed, not proven,
    and the tailorer may only draw on verified bullets.

    Args:
        conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn).
        user_id: The owning user.
        zip_path: LinkedIn export archive.
        resume_path: PDF/DOCX/TXT résumé.

    Returns:
        Counts of rows written: bullets, connections, skills.
    """
    if not zip_path and not resume_path:
        raise ValueError("Provide a LinkedIn export, a résumé, or both")

    profile = parse_linkedin_export(zip_path) if zip_path else LinkedInProfile()

    positions = list(profile.positions)
    skills = list(profile.skills)

    if resume_path:
        from jobos.onboarding.resume_parser import parse_uploaded_resume

        parsed = await parse_uploaded_resume(resume_path)
        known = {(p["company"].lower(), p["title"].lower()) for p in positions}
        for entry in parsed.get("experience") or []:
            company = str(entry.get("company") or "").strip()
            title = str(entry.get("title") or "").strip()
            if company and (company.lower(), title.lower()) not in known:
                positions.append(
                    {
                        "company": company,
                        "title": title,
                        "description": " ".join(entry.get("bullets") or []),
                        "location": "",
                        "started_on": str(entry.get("start") or ""),
                        "finished_on": str(entry.get("end") or ""),
                    }
                )
        skills.extend(s for s in (parsed.get("skills") or []) if s not in skills)

    bullets = 0
    for position in positions:
        for text in _bullet_texts(position):
            written = await conn.fetchval(
                """
                INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status)
                SELECT gen_random_uuid(), $1::uuid, $2, $3, $4, 'unverified'
                WHERE NOT EXISTS (
                    SELECT 1 FROM cg_bullets
                     WHERE user_id = $1::uuid AND company = $2 AND bullet_text = $4
                )
                RETURNING id
                """,
                user_id,
                position["company"],
                position["title"],
                text,
            )
            if written is not None:
                bullets += 1

    connections = 0
    for contact in profile.connections:
        if not contact["name"]:
            continue
        written = await conn.fetchval(
            """
            INSERT INTO people (id, user_id, full_name, title, company_domain, linkedin_url, email, source)
            SELECT gen_random_uuid(), $1::uuid, $2, $3, $4, $5, NULLIF($6, ''), 'linkedin_connection'
            WHERE NOT EXISTS (
                SELECT 1 FROM people
                 WHERE user_id = $1::uuid AND full_name = $2 AND company_domain = $4
            )
            RETURNING id
            """,
            user_id,
            contact["name"],
            contact["title"],
            contact["company"],
            contact["linkedin_url"],
            contact["email"],
        )
        if written is not None:
            connections += 1

    if skills:
        await conn.execute(
            """
            INSERT INTO agent_decisions (id, user_id, module, action, inputs, outputs)
            VALUES (gen_random_uuid(), $1::uuid, 'onboarding', 'import_skills', '{}'::jsonb, $2::jsonb)
            """,
            user_id,
            json.dumps({"skills": skills}),
        )

    logger.info(
        "profile_imported", user_id=user_id, bullets=bullets, connections=connections, skills=len(skills)
    )
    return {"bullets": bullets, "connections": connections, "skills": len(skills)}


def _bullet_texts(position: dict[str, Any]) -> list[str]:
    """Split a position's description into individual achievement bullets."""
    description = position.get("description") or ""
    lines = [line.strip(" •-\t") for line in description.splitlines()]
    bullets = [line for line in lines if len(line) > 20]
    if bullets:
        return bullets
    # No description: record the role itself so the position is not lost.
    if position.get("company") and position.get("title"):
        return [f"{position['title']} at {position['company']}"]
    return []
