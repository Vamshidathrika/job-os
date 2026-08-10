# First Real Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make JOBOS execute end to end on one operator's real data — LinkedIn export and résumé in, ranked jobs and review-gated warm-path outreach out — using only free-tier credentials.

**Architecture:** Six new components wire together engines that already exist and are tested but have zero call sites. A new `jobos/runner/` package sequences them behind a `jobos` CLI; `jobos/workers/` keeps units of work. Embeddings move local so matching needs no credential. Nothing sends without human approval.

**Tech Stack:** Python 3.11, FastAPI, asyncpg + Postgres 16 (RLS), alembic, litellm (Groq free tier), Composio (Gmail), fastembed (local ONNX embeddings), pytest.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-10-first-real-run-design.md`
- **Never scrape LinkedIn.** Profile data comes only from the operator's own export ZIP. The official API scope (`w_member_social`) is post-only.
- **Fail closed on anything reaching a human.** Suppression, daily cap and entailment failures block the send. No verdict never means approved.
- **Never fabricate.** Missing data yields empty fields, not invented ones.
- **Every stage idempotent.** All writes upsert on a natural key; re-running repairs rather than duplicates.
- **Tenant-scoped DB access** uses `jobos.db.pool.tenant_conn`; global tables (`companies`, `jobs`, `suppression_list`) use `global_conn`.
- **Shadow mode stays on.** Outbound work queues to Band B.
- **Existing suite is 275 passing and must stay green.** Run `python -m pytest tests/ -q` before every commit.
- **Test DB:** `postgresql://jobos:jobos_dev@localhost:5432/jobos_test`, schema created by `tests/conftest.py`.
- **Async tests** use `pytest.mark.asyncio(loop_scope="session")` and the `tenant_a_conn` / `db_pool` fixtures.

## Execution Waves (dependency-ordered)

| Wave | Tasks | Depends on |
|---|---|---|
| 1 | Task 1 (embeddings), Task 2 (importer), Task 3 (seeding), Task 5 (handlers) | nothing — fully parallel |
| 2 | Task 4 (matching), Task 6 (race wiring) | T1 / T2 respectively |
| 3 | Task 7 (CLI orchestrator) | all of the above |

---

### Task 1: Local embeddings

**Files:**
- Modify: `jobos/config.py` (LLMSettings)
- Modify: `jobos/db/models.py:6` (`EMBEDDING_DIM`)
- Modify: `jobos/ingestion/embedder.py`
- Create: `alembic/versions/<rev>_embedding_dim_384.py`
- Modify: `pyproject.toml` (dependencies)
- Test: `tests/unit/test_embedder.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `generate_embedding(text: str, settings: Settings | None = None) -> list[float]` returning exactly `EMBEDDING_DIM` (384) floats. `jobos.db.models.EMBEDDING_DIM == 384`.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml` under `dependencies`, add:

```
    "fastembed>=0.4.0",
```

Then run: `pip install 'fastembed>=0.4.0'`

- [ ] **Step 2: Write the failing test**

Create `tests/unit/test_embedder.py`:

```python
"""Tests for local embedding generation."""

import pytest

from jobos.db.models import EMBEDDING_DIM
from jobos.ingestion.embedder import generate_embedding


def test_embedding_dim_matches_local_model():
    assert EMBEDDING_DIM == 384


@pytest.mark.asyncio
async def test_embedding_has_the_column_width():
    vector = await generate_embedding("Backend engineer with Redis experience")

    assert len(vector) == EMBEDDING_DIM
    assert all(isinstance(v, float) for v in vector)


@pytest.mark.asyncio
async def test_similar_text_scores_higher_than_unrelated():
    """A real model must rank a paraphrase above an unrelated sentence."""
    from jobos.matcher.scorer import compute_similarity

    anchor = await generate_embedding("backend engineer building caching layers")
    near = await generate_embedding("server-side developer working on caches")
    far = await generate_embedding("pastry chef specialising in croissants")

    assert compute_similarity(anchor, near) > compute_similarity(anchor, far)


@pytest.mark.asyncio
async def test_empty_text_is_rejected():
    with pytest.raises(ValueError):
        await generate_embedding("   ")
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `python -m pytest tests/unit/test_embedder.py -q`
Expected: FAIL — `assert 768 == 384`.

- [ ] **Step 4: Set the dimension**

In `jobos/db/models.py`, change the constant and its comment:

```python
# Dimension of the job embedding vector. MUST match the output width of the
# configured LLMSettings.embedding_model — the default local
# 'BAAI/bge-small-en-v1.5' emits 384 floats. Changing the model to one with a
# different width requires a migration that ALTERs this column.
EMBEDDING_DIM = 384
```

- [ ] **Step 5: Point config at the local model**

In `jobos/config.py`, in `LLMSettings`, replace the `embedding_model` line:

```python
    # Local ONNX model — no API key, no quota, no network at inference time.
    # Set to a litellm route (e.g. 'cloudflare/@cf/baai/bge-base-en-v1.5') to
    # use a hosted provider instead; EMBEDDING_DIM must then match its width.
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_local: bool = True
```

- [ ] **Step 6: Implement local embedding**

Replace the body of `jobos/ingestion/embedder.py`:

```python
"""Embedder for jobs."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import structlog
from litellm import aembedding

if TYPE_CHECKING:
    from jobos.config import Settings

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _local_model(model_name: str) -> Any:
    """Load the ONNX embedding model once per process.

    The first call downloads roughly 50MB to the fastembed cache; subsequent
    runs are offline.
    """
    from fastembed import TextEmbedding

    logger.info("loading_local_embedding_model", model=model_name)
    return TextEmbedding(model_name=model_name)


async def generate_embedding(text: str, settings: Settings | None = None) -> list[float]:
    """Generate an embedding for job title + description snippet.

    Runs a local ONNX model by default so matching needs no credential. Set
    LLMSettings.embedding_local to False to route through litellm instead.

    Raises:
        ValueError: if the text is empty — an all-zero vector would silently
            match everything.
    """
    if settings is None:
        from jobos.config import settings as default_settings

        settings = default_settings

    if not text.strip():
        raise ValueError("Cannot embed empty text")

    model = settings.llm.embedding_model

    if settings.llm.embedding_local:
        def _embed() -> list[float]:
            vectors = list(_local_model(model).embed([text]))
            return [float(v) for v in vectors[0]]

        # fastembed is synchronous CPU work; keep it off the event loop.
        return await asyncio.to_thread(_embed)

    try:
        response = await aembedding(model=model, input=[text])
        return [float(v) for v in response["data"][0]["embedding"]]
    except Exception as e:
        logger.error("embedding_generation_failed", error=str(e), model=model)
        raise
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/unit/test_embedder.py -q`
Expected: PASS (4 tests). First run downloads the model.

- [ ] **Step 8: Write the migration**

Run: `alembic revision -m "embedding dim 384 for local model"`

In the generated file, add the import and bodies:

```python
from jobos.db.models import EMBEDDING_DIM


def upgrade() -> None:
    # Existing vectors are the wrong width for the new model, and a vector
    # column cannot be re-typed while populated with a different dimension.
    op.execute("UPDATE jobs SET embedding = NULL;")
    op.execute(f"ALTER TABLE jobs ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM});")


def downgrade() -> None:
    op.execute("UPDATE jobs SET embedding = NULL;")
    op.execute("ALTER TABLE jobs ALTER COLUMN embedding TYPE vector(768);")
```

- [ ] **Step 9: Apply and verify the full suite**

Run:
```bash
alembic upgrade head
psql -U jobos -d jobos_test -h localhost -c "DROP TABLE IF EXISTS jobs CASCADE;"
python -m pytest tests/ -q
```
Expected: all pass (275 + 4 new).

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml jobos/config.py jobos/db/models.py jobos/ingestion/embedder.py alembic/versions/ tests/unit/test_embedder.py
git commit -m "feat(embeddings): run bge-small locally so matching needs no credential"
```

---

### Task 2: LinkedIn profile importer

**Files:**
- Create: `jobos/onboarding/linkedin_import.py`
- Create: `alembic/versions/<rev>_people_source.py`
- Modify: `jobos/db/models.py` (PEOPLE_DDL)
- Test: `tests/unit/test_linkedin_import.py`, `tests/integration/test_profile_import.py`

**Interfaces:**
- Consumes: `jobos.onboarding.resume_parser.parse_uploaded_resume`.
- Produces:
  - `parse_linkedin_export(zip_path: str) -> LinkedInProfile`
  - `LinkedInProfile` dataclass with fields `positions: list[dict]`, `education: list[dict]`, `skills: list[str]`, `connections: list[dict]`
  - `async import_profile(conn, user_id: str, zip_path: str | None = None, resume_path: str | None = None) -> dict[str, int]` returning counts `{"bullets": int, "connections": int, "skills": int}`

- [ ] **Step 1: Add the provenance column to the schema**

In `jobos/db/models.py`, in `PEOPLE_DDL`, add after `linkedin_url text,`:

```
    source text,
```

- [ ] **Step 2: Write the failing parser test**

Create `tests/unit/test_linkedin_import.py`:

```python
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
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python -m pytest tests/unit/test_linkedin_import.py -q`
Expected: FAIL — `ModuleNotFoundError: jobos.onboarding.linkedin_import`.

- [ ] **Step 4: Implement the parser**

Create `jobos/onboarding/linkedin_import.py`:

```python
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
```

- [ ] **Step 5: Run the parser tests**

Run: `python -m pytest tests/unit/test_linkedin_import.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Write the failing import test**

Create `tests/integration/test_profile_import.py`:

```python
"""Integration tests for importing a profile into the Career Graph."""

import csv
import io
import zipfile

import pytest

from jobos.onboarding.linkedin_import import import_profile

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _csv(rows):
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue()


@pytest.fixture
def export_zip(tmp_path):
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "Positions.csv",
            _csv([
                ["Company Name", "Title", "Description", "Location", "Started On", "Finished On"],
                ["Acme", "Backend Engineer", "Built a Redis cache cutting p99 45%", "Bengaluru", "Jan 2022", "Mar 2024"],
            ]),
        )
        archive.writestr("Skills.csv", _csv([["Name"], ["Python"]]))
        archive.writestr(
            "Connections.csv",
            _csv([
                ["First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"],
                ["Ravi", "Kumar", "https://linkedin.com/in/ravi", "", "Globex", "Engineering Manager", "01 Feb 2024"],
            ]),
        )
    return str(path)


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people")
    yield
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people")


async def test_positions_become_unverified_bullets(tenant_a_conn, tenant_a_id, export_zip):
    counts = await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)

    assert counts["bullets"] >= 1
    row = await tenant_a_conn.fetchrow(
        "SELECT company, role, bullet_text, verification_status FROM cg_bullets LIMIT 1"
    )
    assert row["company"] == "Acme"
    assert row["verification_status"] == "unverified", (
        "imported history is claimed, not verified; the tailorer may only use verified bullets"
    )


async def test_connections_become_people(tenant_a_conn, tenant_a_id, export_zip):
    counts = await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)

    assert counts["connections"] == 1
    row = await tenant_a_conn.fetchrow("SELECT full_name, company_domain, source FROM people")
    assert row["full_name"] == "Ravi Kumar"
    assert row["source"] == "linkedin_connection"


async def test_import_is_idempotent(tenant_a_conn, tenant_a_id, export_zip):
    await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)
    await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)

    assert await tenant_a_conn.fetchval("SELECT count(*) FROM people") == 1
    bullets = await tenant_a_conn.fetchval("SELECT count(*) FROM cg_bullets")
    assert bullets >= 1
    assert bullets < 4, "re-import must not duplicate bullets"


async def test_import_is_tenant_isolated(tenant_a_conn, tenant_b_conn, tenant_a_id, export_zip):
    await import_profile(tenant_a_conn, str(tenant_a_id), zip_path=export_zip)

    assert await tenant_b_conn.fetchval("SELECT count(*) FROM people") == 0
```

- [ ] **Step 7: Run it to verify it fails**

Run: `python -m pytest tests/integration/test_profile_import.py -q`
Expected: FAIL — `ImportError: cannot import name 'import_profile'`.

- [ ] **Step 8: Implement the importer**

Append to `jobos/onboarding/linkedin_import.py`:

```python
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
```

- [ ] **Step 9: Run the integration tests**

Run: `python -m pytest tests/integration/test_profile_import.py -q`
Expected: FAIL — `column "source" of relation "people" does not exist`.

- [ ] **Step 10: Write and apply the migration**

Run: `alembic revision -m "add people.source"`

Bodies:

```python
def upgrade() -> None:
    # Provenance for a contact: 'linkedin_connection', 'apollo', etc.
    op.execute("ALTER TABLE people ADD COLUMN IF NOT EXISTS source text;")


def downgrade() -> None:
    op.execute("ALTER TABLE people DROP COLUMN IF EXISTS source;")
```

Then run:
```bash
alembic upgrade head
psql -U jobos -d jobos_test -h localhost -c "ALTER TABLE people ADD COLUMN IF NOT EXISTS source text;"
python -m pytest tests/integration/test_profile_import.py -q
```
Expected: PASS (4 tests).

- [ ] **Step 11: Run the full suite and commit**

```bash
python -m pytest tests/ -q
git add jobos/onboarding/linkedin_import.py jobos/db/models.py alembic/versions/ tests/unit/test_linkedin_import.py tests/integration/test_profile_import.py
git commit -m "feat(onboarding): import LinkedIn export and resume into the Career Graph"
```

---

### Task 3: Company universe seeding

**Files:**
- Create: `jobos/ingestion/seed_companies.py`
- Create: `data/seed_companies.yaml`
- Modify: `pyproject.toml` (add `pyyaml`)
- Test: `tests/integration/test_seed_companies.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `async seed_companies(conn, path: str | None = None) -> dict[str, int]` returning `{"inserted": int, "updated": int}`. Reads `data/seed_companies.yaml` by default. Writes to the global `companies` table (no RLS).

- [ ] **Step 1: Add the dependency**

In `pyproject.toml` dependencies add `"pyyaml>=6.0"`, then `pip install 'pyyaml>=6.0'`.

- [ ] **Step 2: Create the seed data**

Create `data/seed_companies.yaml`:

```yaml
# Companies whose public job boards JOBOS polls.
# ats_type: greenhouse | lever | ashby
# ats_identifier: the board token in the public URL, e.g.
#   https://boards-api.greenhouse.io/v1/boards/<ats_identifier>/jobs
#   https://api.lever.co/v0/postings/<ats_identifier>
# Edit freely — this is a starting point, not a fixed list.
companies:
  - name: Razorpay
    domain: razorpay.com
    ats_type: lever
    ats_identifier: razorpay
  - name: Zerodha
    domain: zerodha.com
    ats_type: lever
    ats_identifier: zerodha
  - name: Postman
    domain: postman.com
    ats_type: greenhouse
    ats_identifier: postman
  - name: Freshworks
    domain: freshworks.com
    ats_type: greenhouse
    ats_identifier: freshworks
  - name: Hasura
    domain: hasura.io
    ats_type: greenhouse
    ats_identifier: hasura
  - name: Chargebee
    domain: chargebee.com
    ats_type: lever
    ats_identifier: chargebee
  - name: Zoho
    domain: zoho.com
    ats_type: greenhouse
    ats_identifier: zoho
  - name: Swiggy
    domain: swiggy.com
    ats_type: lever
    ats_identifier: swiggy
```

- [ ] **Step 3: Write the failing test**

Create `tests/integration/test_seed_companies.py`:

```python
"""Integration tests for seeding the company universe."""

import pytest

from jobos.ingestion.seed_companies import seed_companies

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

YAML = """
companies:
  - name: Acme
    domain: acme.example
    ats_type: greenhouse
    ats_identifier: acme
  - name: Globex
    domain: globex.example
    ats_type: lever
    ats_identifier: globex
"""


@pytest.fixture
def seed_file(tmp_path):
    path = tmp_path / "seed.yaml"
    path.write_text(YAML)
    return str(path)


@pytest.fixture(autouse=True)
async def clean(db_pool, setup_schema):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")
    yield
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")


async def test_seeding_inserts_companies(db_pool, seed_file):
    async with db_pool.acquire() as conn:
        counts = await seed_companies(conn, seed_file)

        assert counts["inserted"] == 2
        row = await conn.fetchrow("SELECT * FROM companies WHERE domain = 'acme.example'")
        assert row["ats_type"] == "greenhouse"
        assert row["ats_identifier"] == "acme"


async def test_seeding_is_idempotent(db_pool, seed_file):
    async with db_pool.acquire() as conn:
        await seed_companies(conn, seed_file)
        counts = await seed_companies(conn, seed_file)

        assert counts["inserted"] == 0
        assert counts["updated"] == 2
        total = await conn.fetchval(
            "SELECT count(*) FROM companies WHERE domain LIKE '%.example'"
        )
        assert total == 2


async def test_entry_missing_required_fields_is_rejected(db_pool, tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("companies:\n  - name: NoDomain\n")

    async with db_pool.acquire() as conn:
        with pytest.raises(ValueError, match="domain"):
            await seed_companies(conn, str(path))


async def test_seeded_companies_are_pollable(db_pool, seed_file):
    """The ingestion worker only polls rows with both ATS fields set."""
    async with db_pool.acquire() as conn:
        await seed_companies(conn, seed_file)
        pollable = await conn.fetchval(
            "SELECT count(*) FROM companies "
            "WHERE domain LIKE '%.example' AND ats_type IS NOT NULL AND ats_identifier IS NOT NULL"
        )
    assert pollable == 2
```

- [ ] **Step 4: Run it to verify it fails**

Run: `python -m pytest tests/integration/test_seed_companies.py -q`
Expected: FAIL — `ModuleNotFoundError: jobos.ingestion.seed_companies`.

- [ ] **Step 5: Implement seeding**

Create `jobos/ingestion/seed_companies.py`:

```python
"""Seed the global company universe that the ingestion worker polls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_companies.yaml"

REQUIRED_FIELDS = ("name", "domain", "ats_type", "ats_identifier")
SUPPORTED_ATS = ("greenhouse", "lever", "ashby", "workday")


async def seed_companies(conn: Any, path: str | None = None) -> dict[str, int]:
    """Upsert the seed company list into the global `companies` table.

    Without this the ingestion worker polls an empty universe and silently
    fetches nothing.

    Args:
        conn: A global (non-tenant) connection — `companies` has no RLS.
        path: Seed YAML; defaults to data/seed_companies.yaml.

    Returns:
        Counts of rows inserted and updated.

    Raises:
        ValueError: if an entry is missing a required field or names an
            unsupported ATS.
    """
    seed_path = Path(path) if path else DEFAULT_SEED_PATH
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    payload = yaml.safe_load(seed_path.read_text()) or {}
    entries = payload.get("companies") or []

    inserted = updated = 0
    for entry in entries:
        for required in REQUIRED_FIELDS:
            if not str(entry.get(required, "")).strip():
                raise ValueError(f"Seed entry {entry!r} is missing {required!r}")
        if entry["ats_type"] not in SUPPORTED_ATS:
            raise ValueError(
                f"Unsupported ats_type {entry['ats_type']!r}; expected one of {SUPPORTED_ATS}"
            )

        was_insert = await conn.fetchval(
            """
            INSERT INTO companies (name, domain, ats_type, ats_identifier)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (domain) DO UPDATE
                SET name = EXCLUDED.name,
                    ats_type = EXCLUDED.ats_type,
                    ats_identifier = EXCLUDED.ats_identifier,
                    updated_at = now()
            RETURNING (xmax = 0)
            """,
            entry["name"],
            entry["domain"],
            entry["ats_type"],
            entry["ats_identifier"],
        )
        if was_insert:
            inserted += 1
        else:
            updated += 1

    logger.info("companies_seeded", inserted=inserted, updated=updated, source=str(seed_path))
    return {"inserted": inserted, "updated": updated}
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/integration/test_seed_companies.py -q`
Expected: PASS (4 tests).

- [ ] **Step 7: Run the full suite and commit**

```bash
python -m pytest tests/ -q
git add pyproject.toml data/seed_companies.yaml jobos/ingestion/seed_companies.py tests/integration/test_seed_companies.py
git commit -m "feat(ingestion): seed the company universe the poller reads"
```

---

### Task 5: Action handlers

*(Numbered to match the spec's component list; independent of Tasks 1–3, so it runs in Wave 1.)*

**Files:**
- Create: `jobos/runner/__init__.py`
- Create: `jobos/runner/handlers.py`
- Test: `tests/integration/test_action_handlers.py`

**Interfaces:**
- Consumes: `jobos.outbox.send_email_guarded`, `jobos.integrations.gmail.GmailClient`, `jobos.action_queue.executor.ActionExecutor`.
- Produces: `build_handlers(conn, tenant_id: str, gmail: Any | None = None) -> dict[str, ActionHandler]` mapping `action_type` to an async handler. Keys: `"referral_touch"`, `"submit_application"`, `"publish_post"`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_action_handlers.py`:

```python
"""Integration tests for action handlers wired to the executor."""

import pytest

from jobos.action_queue.executor import ActionExecutor
from jobos.action_queue.queue import ActionQueue
from jobos.referral.suppression import add_to_suppression
from jobos.runner.handlers import build_handlers

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


class FakeGmail:
    def __init__(self):
        self.sent = []

    async def send_email(self, to, subject, body, reply_to=None):
        self.sent.append(to)
        return {"message_id": "sent-1", "status": "sent"}


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM action_queue")
    await tenant_a_conn.execute("DELETE FROM suppression_list")
    yield
    await tenant_a_conn.execute("DELETE FROM action_queue")
    await tenant_a_conn.execute("DELETE FROM suppression_list")


async def test_referral_touch_sends_through_the_guarded_path(tenant_a_conn, tenant_a_id):
    gmail = FakeGmail()
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue(
        "referral_touch",
        {"to": "ravi@globex.example", "subject": "Hello", "body": "Hi Ravi"},
        band="A",
    )

    executor = ActionExecutor(
        queue, handlers=build_handlers(tenant_a_conn, str(tenant_a_id), gmail=gmail)
    )
    result = await executor.process_band_a()

    assert result == {"executed": 1, "failed": 0}
    assert gmail.sent == ["ravi@globex.example"]
    status = await tenant_a_conn.fetchval(
        "SELECT status FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert status == "completed"


async def test_suppressed_recipient_fails_the_action(tenant_a_conn, tenant_a_id):
    """The guard must hold even when reached through the executor."""
    await add_to_suppression(tenant_a_conn, "optedout@globex.example")
    gmail = FakeGmail()
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue(
        "referral_touch",
        {"to": "optedout@globex.example", "subject": "s", "body": "b"},
        band="A",
    )

    executor = ActionExecutor(
        queue, handlers=build_handlers(tenant_a_conn, str(tenant_a_id), gmail=gmail)
    )
    result = await executor.process_band_a()

    assert result == {"executed": 0, "failed": 1}
    assert gmail.sent == []


async def test_touch_without_a_recipient_fails_loudly(tenant_a_conn, tenant_a_id):
    gmail = FakeGmail()
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue("referral_touch", {"subject": "s", "body": "b"}, band="A")

    executor = ActionExecutor(
        queue, handlers=build_handlers(tenant_a_conn, str(tenant_a_id), gmail=gmail)
    )
    result = await executor.process_band_a()

    assert result == {"executed": 0, "failed": 1}
    assert gmail.sent == []


async def test_unimplemented_actions_refuse(tenant_a_conn, tenant_a_id):
    """Cold apply and posting must not report success they cannot deliver."""
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue("submit_application", {"job_url": "https://x.example"}, band="A")
    await queue.enqueue("publish_post", {"content": "hello"}, band="A")

    executor = ActionExecutor(
        queue, handlers=build_handlers(tenant_a_conn, str(tenant_a_id), gmail=FakeGmail())
    )
    result = await executor.process_band_a()

    assert result == {"executed": 0, "failed": 2}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/integration/test_action_handlers.py -q`
Expected: FAIL — `ModuleNotFoundError: jobos.runner`.

- [ ] **Step 3: Create the package**

Create `jobos/runner/__init__.py`:

```python
"""Orchestration: sequences the workers and owns the process lifecycle."""
```

- [ ] **Step 4: Implement the handlers**

Create `jobos/runner/handlers.py`:

```python
"""Handlers the ActionExecutor dispatches to, by action_type.

Handlers are built per request rather than registered globally so each one
closes over the tenant-scoped connection that RLS requires.
"""

from __future__ import annotations

from typing import Any

import structlog

from jobos.outbox import send_email_guarded

logger = structlog.get_logger(__name__)


def build_handlers(
    conn: Any, tenant_id: str, gmail: Any | None = None
) -> dict[str, Any]:
    """Build the action_type -> handler map for one tenant.

    Args:
        conn: A tenant-scoped connection.
        tenant_id: The acting tenant.
        gmail: A GmailClient; constructed per tenant if omitted.
    """
    if gmail is None:
        from jobos.integrations.gmail import GmailClient

        gmail = GmailClient(tenant_id=tenant_id)

    async def referral_touch(payload: dict[str, Any]) -> dict[str, Any]:
        """Send one touch of an outreach sequence via the guarded send path."""
        recipient = payload.get("to")
        if not recipient:
            # Better to fail the action than to send nowhere and mark it done.
            raise ValueError("referral_touch payload has no 'to' address")

        return await send_email_guarded(
            conn,
            gmail,
            tenant_id=tenant_id,
            to=recipient,
            subject=payload.get("subject", ""),
            body=payload.get("body", ""),
        )

    async def submit_application(payload: dict[str, Any]) -> dict[str, Any]:
        """Cold apply is not implemented; refuse rather than claim success."""
        from jobos.cold_apply.executor import ColdApplyExecutor

        executor = ColdApplyExecutor(tenant_id=tenant_id)
        return await executor.submit_application(payload.get("job_url", ""), dry_run=False)

    async def publish_post(payload: dict[str, Any]) -> dict[str, Any]:
        """LinkedIn publishing is not wired up yet."""
        raise NotImplementedError(
            "Publishing is not implemented: it needs a LinkedIn connected account "
            "via Composio. Refusing rather than marking the post as published."
        )

    return {
        "referral_touch": referral_touch,
        "submit_application": submit_application,
        "publish_post": publish_post,
    }
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/integration/test_action_handlers.py -q`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full suite and commit**

```bash
python -m pytest tests/ -q
git add jobos/runner/ tests/integration/test_action_handlers.py
git commit -m "feat(runner): register action handlers so queued work actually executes"
```

---

### Task 4: Matching pipeline

**Depends on Task 1** (needs `EMBEDDING_DIM == 384` and local `generate_embedding`).

**Files:**
- Create: `jobos/matcher/pipeline.py`
- Test: `tests/integration/test_matching_pipeline.py`

**Interfaces:**
- Consumes: `generate_embedding` (Task 1), `compute_similarity`, `compute_requirement_match`, `predict_salary_band`, `calculate_ev`, `classify_tier`.
- Produces: `async run_matching(conn, user_id: str, limit: int = 500) -> dict[str, int]` returning `{"scored": int, "tier_1": int}`; writes `matches` rows with `score`, `ev_score`, `tier`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_matching_pipeline.py`:

```python
"""Integration tests for the matching pipeline."""

import uuid

import pytest

from jobos.db.models import EMBEDDING_DIM
from jobos.matcher.pipeline import build_profile_text, run_matching

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")
    yield
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")


async def _seed_job(db_pool, title: str, description: str) -> uuid.UUID:
    async with db_pool.acquire() as conn:
        company_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO companies (id, name, domain) VALUES ($1, $2, $3)",
            company_id, "Acme", f"acme-{company_id.hex[:8]}.example",
        )
        job_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO jobs (id, company_id, external_id, title, description, country, embedding) "
            "VALUES ($1, $2, $3, $4, $5, 'IN', $6::vector)",
            job_id, company_id, f"ext-{job_id.hex[:6]}", title, description,
            str([0.01] * EMBEDDING_DIM),
        )
        return job_id


async def test_matching_writes_scored_rows(tenant_a_conn, tenant_a_id, db_pool):
    job_id = await _seed_job(db_pool, "Backend Engineer", "Python, Postgres, caching")
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Acme', 'Backend Engineer', 'Built Redis caches in Python', 'verified')",
        tenant_a_id,
    )

    counts = await run_matching(tenant_a_conn, str(tenant_a_id))

    assert counts["scored"] == 1
    row = await tenant_a_conn.fetchrow(
        "SELECT job_id, score, ev_score, tier FROM matches WHERE job_id = $1", job_id
    )
    assert row is not None
    assert 0.0 <= row["score"] <= 1.0
    assert row["ev_score"] > 0
    assert row["tier"] in (1, 2, 3)


async def test_matching_is_idempotent(tenant_a_conn, tenant_a_id, db_pool):
    await _seed_job(db_pool, "Backend Engineer", "Python")
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Acme', 'Engineer', 'Built things in Python', 'verified')",
        tenant_a_id,
    )

    await run_matching(tenant_a_conn, str(tenant_a_id))
    await run_matching(tenant_a_conn, str(tenant_a_id))

    assert await tenant_a_conn.fetchval("SELECT count(*) FROM matches") == 1


async def test_no_profile_scores_nothing(tenant_a_conn, tenant_a_id, db_pool):
    """With no career history there is nothing to match against."""
    await _seed_job(db_pool, "Backend Engineer", "Python")

    counts = await run_matching(tenant_a_conn, str(tenant_a_id))

    assert counts["scored"] == 0


async def test_profile_text_uses_the_career_graph():
    bullets = [
        {"bullet_text": "Built Redis caches", "role": "Backend Engineer", "company": "Acme"},
        {"bullet_text": "Led a team of 4", "role": "Backend Engineer", "company": "Acme"},
    ]
    text = build_profile_text(bullets)

    assert "Redis" in text
    assert "Backend Engineer" in text


async def test_matches_are_tenant_isolated(tenant_a_conn, tenant_b_conn, tenant_a_id, db_pool):
    await _seed_job(db_pool, "Backend Engineer", "Python")
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Acme', 'Engineer', 'Built things in Python', 'verified')",
        tenant_a_id,
    )
    await run_matching(tenant_a_conn, str(tenant_a_id))

    assert await tenant_b_conn.fetchval("SELECT count(*) FROM matches") == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/integration/test_matching_pipeline.py -q`
Expected: FAIL — `ModuleNotFoundError: jobos.matcher.pipeline`.

- [ ] **Step 3: Implement the pipeline**

Create `jobos/matcher/pipeline.py`:

```python
"""Sequences scoring, EV and tiering over ingested jobs.

This is the glue between ingestion and the warm-path race. Every function it
calls already exists and is tested; this module only orders them and persists
the outcome.
"""

from __future__ import annotations

from typing import Any

import structlog

from jobos.comp.predictor import predict_salary_band
from jobos.ingestion.embedder import generate_embedding
from jobos.matcher.ev_ranker import calculate_ev
from jobos.matcher.scorer import compute_similarity
from jobos.matcher.tier_gate import classify_tier

logger = structlog.get_logger(__name__)

# Similarity is a weak proxy for offer probability, so it is damped rather
# than used directly: a 0.8 cosine match is not an 80% chance of an offer.
P_OFFER_SCALE = 0.35

# Normalises EV (rupees) onto the 0-1 scale classify_tier expects.
EV_NORMALISATION_INR = 5_000_000.0


def build_profile_text(bullets: list[dict[str, Any]]) -> str:
    """Flatten the Career Graph into one document for embedding."""
    parts: list[str] = []
    for bullet in bullets:
        role = bullet.get("role") or ""
        company = bullet.get("company") or ""
        text = bullet.get("bullet_text") or ""
        parts.append(" ".join(p for p in (role, company, text) if p))
    return "\n".join(parts)


async def run_matching(conn: Any, user_id: str, limit: int = 500) -> dict[str, int]:
    """Score every ingested job against the user's Career Graph.

    Args:
        conn: A tenant-scoped connection.
        user_id: The user to match for.
        limit: Maximum jobs to score in one pass.

    Returns:
        Counts of jobs scored and how many landed in Tier 1.
    """
    bullets = [
        dict(row)
        for row in await conn.fetch(
            "SELECT bullet_text, role, company FROM cg_bullets WHERE user_id = $1::uuid",
            user_id,
        )
    ]
    if not bullets:
        logger.warning("matching_skipped_no_career_graph", user_id=user_id)
        return {"scored": 0, "tier_1": 0}

    profile_text = build_profile_text(bullets)
    profile_vector = await generate_embedding(profile_text)

    jobs = await conn.fetch(
        """
        SELECT j.id, j.title, j.description, j.location, j.embedding
          FROM jobs j
         WHERE j.embedding IS NOT NULL
         ORDER BY j.first_seen_at DESC
         LIMIT $1
        """,
        limit,
    )

    scored = tier_1 = 0
    for job in jobs:
        job_vector = _parse_vector(job["embedding"])
        if not job_vector:
            continue

        score = compute_similarity(job_vector, profile_vector)
        band = predict_salary_band(
            title=job["title"] or "", location=job["location"] or "", yoe=_years_of_experience(bullets)
        )
        ev = calculate_ev(p_offer=score * P_OFFER_SCALE, predicted_comp_p50=band["p50"])
        ev_score = min(1.0, ev / EV_NORMALISATION_INR)
        tier = classify_tier(match_score=score, ev_score=ev_score)

        await conn.execute(
            """
            INSERT INTO matches (id, user_id, job_id, score, ev_score, tier)
            VALUES (gen_random_uuid(), $1::uuid, $2, $3, $4, $5)
            ON CONFLICT (user_id, job_id) DO UPDATE
                SET score = EXCLUDED.score,
                    ev_score = EXCLUDED.ev_score,
                    tier = EXCLUDED.tier
            """,
            user_id,
            job["id"],
            score,
            ev_score,
            tier,
        )
        scored += 1
        if tier == 1:
            tier_1 += 1

    logger.info("matching_complete", user_id=user_id, scored=scored, tier_1=tier_1)
    return {"scored": scored, "tier_1": tier_1}


def _parse_vector(raw: Any) -> list[float]:
    """pgvector comes back as a string like '[0.1,0.2]'."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [float(v) for v in raw]
    text = str(raw).strip().strip("[]")
    if not text:
        return []
    return [float(part) for part in text.split(",")]


def _years_of_experience(bullets: list[dict[str, Any]]) -> int:
    """Coarse seniority proxy: distinct employers in the Career Graph.

    A real estimate needs position dates, which the importer records but the
    bullets table does not carry; this keeps comp banding stable until then.
    """
    companies = {b.get("company") for b in bullets if b.get("company")}
    return max(1, len(companies) * 2)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/integration/test_matching_pipeline.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest tests/ -q
git add jobos/matcher/pipeline.py tests/integration/test_matching_pipeline.py
git commit -m "feat(matcher): score ingested jobs against the Career Graph"
```

---

### Task 6: Race wiring from existing connections

**Depends on Task 2** (needs connections in `people`).

**Files:**
- Create: `jobos/runner/warm_paths.py`
- Test: `tests/integration/test_warm_path_wiring.py`

**Interfaces:**
- Consumes: `map_existing_network`, `generate_referral_sequence`, `WarmPathRace`, `should_hold_application`.
- Produces: `async start_races_for_tier_1(conn, user_id: str, settings=None, limit: int = 20) -> dict[str, int]` returning `{"started": int, "no_warm_path": int, "gated": int}`.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_warm_path_wiring.py`:

```python
"""Integration tests wiring Tier-1 matches into warm-path races."""

import json
import uuid

import pytest

from jobos.runner.warm_paths import start_races_for_tier_1

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _sequence_reply() -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        [
                            {"subject": "s1", "body": "b1"},
                            {"subject": "s2", "body": "b2"},
                            {"subject": "s3", "body": "b3"},
                        ]
                    )
                }
            }
        ]
    }


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    for table in ("warm_path_races", "action_queue", "matches", "people"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")
    yield
    for table in ("warm_path_races", "action_queue", "matches", "people"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")


async def _tier_1_job(tenant_a_conn, tenant_a_id, db_pool, company_name="Globex") -> uuid.UUID:
    async with db_pool.acquire() as conn:
        company_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO companies (id, name, domain) VALUES ($1, $2, $3)",
            company_id, company_name, f"{company_name.lower()}.example",
        )
        job_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO jobs (id, company_id, external_id, title) VALUES ($1, $2, $3, $4)",
            job_id, company_id, f"ext-{job_id.hex[:6]}", "Backend Engineer",
        )
    await tenant_a_conn.execute(
        "INSERT INTO matches (id, user_id, job_id, score, ev_score, tier) "
        "VALUES (gen_random_uuid(), $1, $2, 0.8, 0.7, 1)",
        tenant_a_id, job_id,
    )
    return job_id


async def test_race_starts_when_a_connection_works_there(
    tenant_a_conn, tenant_a_id, db_pool, mocker
):
    mocker.patch("jobos.referral.sequence.acompletion", return_value=_sequence_reply())
    job_id = await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, source) "
        "VALUES (gen_random_uuid(), $1, 'Ravi Kumar', 'Globex', 'ravi@globex.example', 'linkedin_connection')",
        tenant_a_id,
    )

    counts = await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    assert counts["started"] == 1
    race = await tenant_a_conn.fetchrow(
        "SELECT status FROM warm_path_races WHERE job_id = $1", job_id
    )
    assert race["status"] == "running"
    touches = await tenant_a_conn.fetchval(
        "SELECT count(*) FROM action_queue WHERE action_type = 'referral_touch'"
    )
    assert touches == 3


async def test_no_connection_means_no_race(tenant_a_conn, tenant_a_id, db_pool):
    """A job where the operator knows nobody must be recorded, not silently skipped."""
    await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)

    counts = await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    assert counts["started"] == 0
    assert counts["no_warm_path"] == 1
    assert await tenant_a_conn.fetchval("SELECT count(*) FROM warm_path_races") == 0


async def test_only_tier_1_jobs_race(tenant_a_conn, tenant_a_id, db_pool, mocker):
    mocker.patch("jobos.referral.sequence.acompletion", return_value=_sequence_reply())
    job_id = await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)
    await tenant_a_conn.execute("UPDATE matches SET tier = 2 WHERE job_id = $1", job_id)

    counts = await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    assert counts["started"] == 0
    assert await tenant_a_conn.fetchval("SELECT count(*) FROM warm_path_races") == 0


async def test_gated_when_no_shared_context(tenant_a_conn, tenant_a_id, db_pool, mocker):
    """The personalisation gate drops contacts with no real common ground."""
    llm = mocker.patch("jobos.referral.sequence.acompletion")
    await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, source) "
        "VALUES (gen_random_uuid(), $1, 'Stranger Person', 'Globex', 's@globex.example', 'apollo')",
        tenant_a_id,
    )

    counts = await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    assert counts["gated"] == 1
    assert counts["started"] == 0
    llm.assert_not_called()


async def test_rerun_does_not_duplicate_touches(tenant_a_conn, tenant_a_id, db_pool, mocker):
    mocker.patch("jobos.referral.sequence.acompletion", return_value=_sequence_reply())
    await _tier_1_job(tenant_a_conn, tenant_a_id, db_pool)
    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, source) "
        "VALUES (gen_random_uuid(), $1, 'Ravi Kumar', 'Globex', 'ravi@globex.example', 'linkedin_connection')",
        tenant_a_id,
    )

    await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))
    await start_races_for_tier_1(tenant_a_conn, str(tenant_a_id))

    touches = await tenant_a_conn.fetchval(
        "SELECT count(*) FROM action_queue WHERE action_type = 'referral_touch'"
    )
    assert touches == 3, "an already-running race must not be restarted"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/integration/test_warm_path_wiring.py -q`
Expected: FAIL — `ModuleNotFoundError: jobos.runner.warm_paths`.

- [ ] **Step 3: Implement the wiring**

Create `jobos/runner/warm_paths.py`:

```python
"""Turn Tier-1 matches into warm-path races.

Referrers come from the operator's own LinkedIn connections rather than a
paid people-search API: Connections.csv already lists everyone they know and
where those people work.
"""

from __future__ import annotations

from typing import Any

import structlog

from jobos.referral.network_mapper import map_existing_network
from jobos.referral.sequence import generate_referral_sequence
from jobos.warm_path.decision import should_hold_application
from jobos.warm_path.race import WarmPathRace

logger = structlog.get_logger(__name__)


async def start_races_for_tier_1(
    conn: Any, user_id: str, settings: Any = None, limit: int = 20
) -> dict[str, int]:
    """Start a warm-path race for each Tier-1 match that has a warm contact.

    Args:
        conn: A tenant-scoped connection.
        user_id: The acting user.
        settings: Application settings, forwarded to sequence generation.
        limit: Maximum races to start in one pass.

    Returns:
        started — races begun;
        no_warm_path — Tier-1 jobs where the operator knows nobody;
        gated — contacts dropped by the personalisation gate.
    """
    candidates = await conn.fetch(
        """
        SELECT m.job_id, m.score, m.ev_score, m.tier, j.title, c.name AS company_name, c.domain
          FROM matches m
          JOIN jobs j ON j.id = m.job_id
          JOIN companies c ON c.id = j.company_id
          LEFT JOIN warm_path_races r ON r.job_id = m.job_id
         WHERE m.tier = 1 AND r.id IS NULL
         ORDER BY m.ev_score DESC
         LIMIT $1
        """,
        limit,
    )

    contacts = [
        dict(row)
        for row in await conn.fetch(
            "SELECT full_name, company_domain, email, title FROM people WHERE user_id = $1::uuid",
            user_id,
        )
    ]

    started = no_warm_path = gated = 0

    for candidate in candidates:
        if not should_hold_application(
            match_score=candidate["score"], ev_score=candidate["ev_score"], tier=candidate["tier"]
        ):
            continue

        company = candidate["company_name"] or candidate["domain"]
        warm = map_existing_network(
            [{**c, "company": c["company_domain"]} for c in contacts], [company]
        )
        warm = await warm if hasattr(warm, "__await__") else warm

        reachable = [w for w in warm if w.get("email")]
        if not reachable:
            no_warm_path += 1
            logger.info("no_warm_path_available", job_id=str(candidate["job_id"]), company=company)
            continue

        referrer = reachable[0]
        touches = await generate_referral_sequence(
            referrer={
                "name": referrer.get("full_name"),
                "title": referrer.get("title"),
                "company_domain": referrer.get("company_domain"),
                # A mutual employer is the shared context that clears the gate.
                "shared_past_company": [company] if referrer.get("source") == "linkedin_connection" else [],
            },
            job={"title": candidate["title"], "company": company},
            user_profile={"name": "the candidate"},
            settings=settings,
        )

        if not touches:
            gated += 1
            logger.info("referral_gated", job_id=str(candidate["job_id"]), company=company)
            continue

        for touch in touches:
            touch["to"] = referrer["email"]

        race = WarmPathRace(conn=conn, job_id=str(candidate["job_id"]), tenant_id=user_id)
        await race.start_race(touches=touches)
        started += 1

    logger.info(
        "tier_1_races_processed", started=started, no_warm_path=no_warm_path, gated=gated
    )
    return {"started": started, "no_warm_path": no_warm_path, "gated": gated}
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/integration/test_warm_path_wiring.py -q`
Expected: PASS (5 tests).

Note: `map_existing_network` is an async function; the `hasattr(..., "__await__")` guard above keeps this working whether it is called as sync or async. If the tests show a coroutine warning, replace those two lines with a direct `await map_existing_network(...)`.

- [ ] **Step 5: Run the full suite and commit**

```bash
python -m pytest tests/ -q
git add jobos/runner/warm_paths.py tests/integration/test_warm_path_wiring.py
git commit -m "feat(runner): start warm-path races from the operator's own connections"
```

---

### Task 7: Orchestrator CLI

**Depends on Tasks 1–6.**

**Files:**
- Create: `jobos/runner/pipeline.py`
- Create: `jobos/cli.py`
- Modify: `pyproject.toml` (`[project.scripts]`)
- Test: `tests/integration/test_pipeline_end_to_end.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `async run_full_pipeline(pool, user_id: str, settings) -> dict[str, dict]` keyed by stage name.
  - `main(argv: list[str] | None = None) -> int` — CLI entry point.

- [ ] **Step 1: Write the failing end-to-end test**

Create `tests/integration/test_pipeline_end_to_end.py`:

```python
"""End-to-end smoke test: the whole pipeline in one run."""

import json

import pytest

from jobos.config import Settings
from jobos.db.models import EMBEDDING_DIM
from jobos.runner.pipeline import run_full_pipeline

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 4242,
            "title": "Backend Engineer",
            "location": {"name": "Bengaluru, India"},
            "content": "Python, Postgres and caching at scale.",
        }
    ]
}


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    for table in ("warm_path_races", "action_queue", "matches", "people", "cg_bullets"):
        await tenant_a_conn.execute(f"DELETE FROM {table}")
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM jobs")
        await conn.execute("DELETE FROM companies WHERE domain LIKE '%.example'")
    yield


async def test_full_pipeline_produces_matches(tenant_a_conn, tenant_a_id, db_pool, tmp_path, mocker):
    mocker.patch(
        "jobos.ingestion.poller.ATSPoller._fetch_with_retry", return_value=GREENHOUSE_PAYLOAD
    )
    mocker.patch(
        "jobos.referral.sequence.acompletion",
        return_value={"choices": [{"message": {"content": json.dumps([
            {"subject": "s1", "body": "b1"},
            {"subject": "s2", "body": "b2"},
            {"subject": "s3", "body": "b3"},
        ])}}]},
    )

    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "companies:\n"
        "  - name: Acme\n"
        "    domain: acme.example\n"
        "    ats_type: greenhouse\n"
        "    ats_identifier: acme\n"
    )

    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Prior Co', 'Backend Engineer', "
        "'Built Python services on Postgres with Redis caching', 'verified')",
        tenant_a_id,
    )

    result = await run_full_pipeline(
        db_pool, str(tenant_a_id), Settings(), seed_path=str(seed)
    )

    assert result["seed"]["inserted"] == 1
    assert result["ingest"]["ingested"] == 1
    assert result["match"]["scored"] == 1

    job_count = await tenant_a_conn.fetchval("SELECT count(*) FROM matches")
    assert job_count == 1


async def test_pipeline_is_idempotent(tenant_a_conn, tenant_a_id, db_pool, tmp_path, mocker):
    mocker.patch(
        "jobos.ingestion.poller.ATSPoller._fetch_with_retry", return_value=GREENHOUSE_PAYLOAD
    )
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "companies:\n  - name: Acme\n    domain: acme.example\n"
        "    ats_type: greenhouse\n    ats_identifier: acme\n"
    )
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1, 'Prior Co', 'Engineer', 'Built Python services', 'verified')",
        tenant_a_id,
    )

    await run_full_pipeline(db_pool, str(tenant_a_id), Settings(), seed_path=str(seed))
    await run_full_pipeline(db_pool, str(tenant_a_id), Settings(), seed_path=str(seed))

    async with db_pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM jobs") == 1
    assert await tenant_a_conn.fetchval("SELECT count(*) FROM matches") == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/integration/test_pipeline_end_to_end.py -q`
Expected: FAIL — `ModuleNotFoundError: jobos.runner.pipeline`.

- [ ] **Step 3: Implement the pipeline**

Create `jobos/runner/pipeline.py`:

```python
"""Sequences the pipeline stages. Each stage is idempotent and independently runnable."""

from __future__ import annotations

from typing import Any

import structlog

from jobos.action_queue.executor import ActionExecutor
from jobos.action_queue.queue import ActionQueue
from jobos.db.pool import global_conn, tenant_conn
from jobos.ingestion.seed_companies import seed_companies
from jobos.matcher.pipeline import run_matching
from jobos.runner.handlers import build_handlers
from jobos.runner.warm_paths import start_races_for_tier_1
from jobos.warm_path.race import WarmPathRace, find_expired_races
from jobos.workers.global_ingestion import GlobalIngestionWorker

logger = structlog.get_logger(__name__)


async def stage_seed(pool: Any, seed_path: str | None = None) -> dict[str, int]:
    """Upsert the company universe."""
    async with global_conn(pool) as conn:
        return await seed_companies(conn, seed_path)


async def stage_ingest(pool: Any, settings: Any) -> dict[str, int]:
    """Poll every seeded board and store the jobs."""
    worker = GlobalIngestionWorker(pool=pool, settings=settings)
    return await worker.run_cycle()


async def stage_match(pool: Any, user_id: str) -> dict[str, int]:
    """Score ingested jobs against the Career Graph."""
    async with tenant_conn(pool, user_id) as conn:
        return await run_matching(conn, user_id)


async def stage_race(pool: Any, user_id: str, settings: Any) -> dict[str, int]:
    """Start races for Tier-1 matches and resolve any that have expired."""
    async with tenant_conn(pool, user_id) as conn:
        started = await start_races_for_tier_1(conn, user_id, settings=settings)

        resolved = 0
        for expired in await find_expired_races(conn):
            race = WarmPathRace(conn=conn, job_id=expired["job_id"], tenant_id=user_id)
            await race.resolve_race()
            resolved += 1

    return {**started, "resolved": resolved}


async def stage_work(pool: Any, user_id: str) -> dict[str, int]:
    """Execute due Band A actions."""
    async with tenant_conn(pool, user_id) as conn:
        queue = ActionQueue(conn=conn, tenant_id=user_id)
        executor = ActionExecutor(queue, handlers=build_handlers(conn, user_id))
        return await executor.process_band_a()


async def run_full_pipeline(
    pool: Any, user_id: str, settings: Any, seed_path: str | None = None
) -> dict[str, dict]:
    """Run every stage in order, returning each stage's counts."""
    logger.info("pipeline_start", user_id=user_id)

    results = {
        "seed": await stage_seed(pool, seed_path),
        "ingest": await stage_ingest(pool, settings),
        "match": await stage_match(pool, user_id),
        "race": await stage_race(pool, user_id, settings),
        "work": await stage_work(pool, user_id),
    }

    logger.info("pipeline_complete", **{k: str(v) for k, v in results.items()})
    return results
```

- [ ] **Step 4: Run the end-to-end tests**

Run: `python -m pytest tests/integration/test_pipeline_end_to_end.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Implement the CLI**

Create `jobos/cli.py`:

```python
"""JOBOS command line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import structlog

from jobos.config import settings
from jobos.db.pool import create_pool, tenant_conn
from jobos.runner.pipeline import (
    run_full_pipeline,
    stage_ingest,
    stage_match,
    stage_race,
    stage_seed,
    stage_work,
)

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobos", description="Autonomous warm-path job search")
    parser.add_argument("--user-id", required=True, help="Tenant/user UUID to act as")
    sub = parser.add_subparsers(dest="command", required=True)

    importer = sub.add_parser("import", help="Import a LinkedIn export and/or resume")
    importer.add_argument("--linkedin-zip")
    importer.add_argument("--resume")

    seed = sub.add_parser("seed", help="Seed the company universe")
    seed.add_argument("--file")

    sub.add_parser("ingest", help="Poll job boards")
    sub.add_parser("match", help="Score jobs against your profile")
    sub.add_parser("race", help="Start and resolve warm-path races")
    sub.add_parser("work", help="Execute due queued actions")

    run = sub.add_parser("run", help="Run the whole pipeline")
    run.add_argument("--seed-file")

    return parser


async def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    pool = await create_pool(settings)
    try:
        if args.command == "import":
            from jobos.onboarding.linkedin_import import import_profile

            async with tenant_conn(pool, args.user_id) as conn:
                return await import_profile(
                    conn, args.user_id, zip_path=args.linkedin_zip, resume_path=args.resume
                )
        if args.command == "seed":
            return await stage_seed(pool, args.file)
        if args.command == "ingest":
            return await stage_ingest(pool, settings)
        if args.command == "match":
            return await stage_match(pool, args.user_id)
        if args.command == "race":
            return await stage_race(pool, args.user_id, settings)
        if args.command == "work":
            return await stage_work(pool, args.user_id)
        return await run_full_pipeline(pool, args.user_id, settings, seed_path=args.seed_file)
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(_dispatch(args))
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Register the entry point**

In `pyproject.toml`, after the `[project]` table add:

```toml
[project.scripts]
jobos = "jobos.cli:main"
```

Then run: `pip install -e .`

- [ ] **Step 7: Verify the CLI runs**

Run: `jobos --help`
Expected: usage text listing `import`, `seed`, `ingest`, `match`, `race`, `work`, `run`.

Run: `jobos --user-id 11111111-1111-1111-1111-111111111111 seed`
Expected: JSON counts, exit 0.

- [ ] **Step 8: Run the full suite and commit**

```bash
python -m pytest tests/ -q
git add jobos/runner/pipeline.py jobos/cli.py pyproject.toml tests/integration/test_pipeline_end_to_end.py
git commit -m "feat(cli): one command runs the whole pipeline"
```

---

## Self-Review

**Spec coverage:**

| Spec component | Task |
|---|---|
| 1. Profile importer | Task 2 |
| 2. Company universe seeding | Task 3 |
| 3. Matching pipeline | Task 4 |
| 4. Orchestrator + CLI | Task 7 |
| 5. Action handlers | Task 5 |
| 6. Race wiring | Task 6 |
| Local embeddings decision | Task 1 |
| `people.source` migration | Task 2, Step 10 |
| Shadow mode / Band B default | Task 6 (touches queue to Band B via `start_race`) |

**Type consistency:** `generate_embedding` returns `list[float]` (T1) and is consumed as such by `run_matching` (T4). `import_profile` returns `dict[str, int]` (T2), consumed by the CLI (T7). `build_handlers` returns `dict[str, ActionHandler]` (T5), consumed by `stage_work` (T7). `start_races_for_tier_1` returns `{"started", "no_warm_path", "gated"}` (T6); `stage_race` adds `"resolved"` (T7). `EMBEDDING_DIM` is 384 everywhere after T1.

**Known follow-ups, deliberately not in this plan:** API authentication (blocking before network exposure), cold apply, Apollo sourcing, LinkedIn publishing.
