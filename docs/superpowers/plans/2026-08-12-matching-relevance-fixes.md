# Matching Relevance Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap between what `jobos/matcher/pipeline.py` actually scores (text similarity + comp) and what real job seekers weigh (skill fit + real chance of a response), per the `research-ops`/`product-manager-toolkit` audit in this session: referrals convert 4–10x better than cold applies but currently only affect outreach *after* tiering, and a tested skill-gap scorer (`compute_requirement_match`) is wired to nothing.

**Architecture:** Two independent-ish changes to the matcher: (1) an extraction step populates the already-existing but always-empty `job_requirements.hard_reqs` column, and `run_matching` calls the existing `compute_requirement_match` against it; (2) `classify_tier` drops its unused `company_tier` param and gains a real `has_warm_contact` signal, computed once per matching run via the existing `map_existing_network` (pure in-memory fuzzy match, no new I/O).

**Tech Stack:** Python/asyncpg/pytest, existing `litellm`/Groq pattern for the new extraction call.

## Global Constraints

- Every LLM call passes `api_key=settings.llm.platform_groq_key or None` explicitly (established fix from this session — do not regress it).
- No fabricated data: extraction failure returns `[]`, never a guessed requirement list.
- TDD throughout: failing test → confirm failure reason → implement → passing test → commit.
- Every new/changed function needs a test; run the full suite (`python -m pytest tests/ -q` from repo root, `.venv` active) before each commit.

---

### Task 1: Hard-requirement extraction and skill-gap scoring

**Files:**
- Create: `jobos/ingestion/requirement_extractor.py`
- Modify: `jobos/ingestion/poller.py` (call the extractor after a job is inserted)
- Modify: `jobos/matcher/pipeline.py` (`run_matching`: compute + persist skill coverage)
- Create migration: `alembic/versions/<new>_add_matches_skill_coverage.py` (adds `matches.skill_coverage float`, `matches.missing_skills jsonb`, both nullable)
- Test: `tests/unit/test_requirement_extractor.py`
- Test: `tests/integration/test_matching_skill_coverage.py`

**Interfaces:**
- Consumes: `jobos.matcher.scorer.compute_requirement_match(hard_reqs: list[str], candidate_skills: list[str]) -> tuple[float, list[str]]` (existing, unchanged).
- Produces: `async def extract_hard_requirements(job_description: str, settings: Any) -> list[str]` in the new file.
- Produces: `matches.skill_coverage` (float 0–1) and `matches.missing_skills` (jsonb list of strings) columns, populated by `run_matching`.

- [ ] **Step 1.1: Write the failing extractor test**

```python
# tests/unit/test_requirement_extractor.py
import pytest
from unittest.mock import AsyncMock, patch

from jobos.ingestion.requirement_extractor import extract_hard_requirements


@pytest.mark.asyncio
async def test_extracts_requirements_from_description(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(
        content='{"hard_requirements": ["Python", "PostgreSQL", "Kubernetes"]}'
    ))]
    mocker.patch(
        "jobos.ingestion.requirement_extractor.acompletion",
        AsyncMock(return_value=mock_response),
    )
    settings = mocker.MagicMock()
    settings.llm.platform_groq_key = "fake-key"
    settings.llm.tailoring_model = "groq/llama-3.1-8b-instant"

    result = await extract_hard_requirements("We need 5+ years Python, PostgreSQL, and K8s experience.", settings)

    assert result == ["Python", "PostgreSQL", "Kubernetes"]


@pytest.mark.asyncio
async def test_returns_empty_list_on_malformed_llm_response(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content="not json"))]
    mocker.patch(
        "jobos.ingestion.requirement_extractor.acompletion",
        AsyncMock(return_value=mock_response),
    )
    settings = mocker.MagicMock()
    settings.llm.platform_groq_key = "fake-key"
    settings.llm.tailoring_model = "groq/llama-3.1-8b-instant"

    result = await extract_hard_requirements("garbage in", settings)

    assert result == []
```

- [ ] **Step 1.2: Run to verify it fails**

Run: `pytest tests/unit/test_requirement_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'jobos.ingestion.requirement_extractor'`

- [ ] **Step 1.3: Implement the extractor**

```python
# jobos/ingestion/requirement_extractor.py
"""Pulls hard requirements out of a job description via LLM.

job_requirements.hard_reqs has existed in the schema since the first
migration but nothing ever wrote to it — this is that writer. Failure
returns [] rather than a guess: an empty requirements list just means
compute_requirement_match treats the job as having no hard gate, not that
the job is lying about needing a skill it doesn't.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion

logger = structlog.get_logger(__name__)

_PROMPT = """Extract the hard (must-have) technical requirements from this \
job description. Return ONLY JSON: {{"hard_requirements": ["skill1", "skill2"]}}. \
If there are none, return {{"hard_requirements": []}}.

Job description:
{description}
"""


async def extract_hard_requirements(job_description: str, settings: Any) -> list[str]:
    if not job_description or not job_description.strip():
        return []
    try:
        response = await acompletion(
            model=settings.llm.tailoring_model,
            messages=[{"role": "user", "content": _PROMPT.format(description=job_description[:4000])}],
            api_key=settings.llm.platform_groq_key or None,
            temperature=0.0,
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        reqs = parsed.get("hard_requirements", [])
        return [str(r) for r in reqs if str(r).strip()]
    except Exception as e:
        logger.warning("requirement_extraction_failed", error=str(e))
        return []
```

- [ ] **Step 1.4: Run to verify it passes**

Run: `pytest tests/unit/test_requirement_extractor.py -v`
Expected: PASS (2 tests)

- [ ] **Step 1.5: Add the migration**

Generate with `alembic revision -m "add matches skill coverage columns"` from the repo root, then edit the generated file:

```python
def upgrade() -> None:
    op.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS skill_coverage float;")
    op.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS missing_skills jsonb;")

def downgrade() -> None:
    op.execute("ALTER TABLE matches DROP COLUMN IF EXISTS skill_coverage;")
    op.execute("ALTER TABLE matches DROP COLUMN IF EXISTS missing_skills;")
```

Run: `alembic upgrade head` against the local dev DB, confirm `alembic heads` shows a single head.

- [ ] **Step 1.6: Write the failing integration test**

```python
# tests/integration/test_matching_skill_coverage.py
import pytest

from jobos.matcher.pipeline import run_matching

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM job_requirements")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    yield
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM job_requirements")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")


async def test_run_matching_persists_skill_coverage(tenant_a_conn, tenant_a_id):
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1::uuid, 'Acme', 'Engineer', 'Built things with Python and PostgreSQL', 'verified')",
        tenant_a_id,
    )
    job_id = await tenant_a_conn.fetchval(
        "SELECT id FROM jobs LIMIT 1"
    )
    if job_id is None:
        pytest.skip("no seeded job available in this fixture DB")

    await tenant_a_conn.execute(
        "INSERT INTO job_requirements (job_id, hard_reqs) VALUES ($1, $2::jsonb) "
        "ON CONFLICT (job_id) DO UPDATE SET hard_reqs = EXCLUDED.hard_reqs",
        job_id, '["Python", "PostgreSQL", "Kubernetes"]',
    )
    await tenant_a_conn.execute(
        "UPDATE jobs SET embedding = (SELECT array_fill(0.1, ARRAY[384])::vector) WHERE id = $1",
        job_id,
    )

    await run_matching(tenant_a_conn, str(tenant_a_id))

    row = await tenant_a_conn.fetchrow(
        "SELECT skill_coverage, missing_skills FROM matches WHERE user_id = $1::uuid AND job_id = $2",
        tenant_a_id, job_id,
    )
    assert row is not None
    assert row["skill_coverage"] == pytest.approx(2 / 3)
    assert "Kubernetes" in row["missing_skills"]
```

Adjust the fixture's job-seeding approach if this repo's test DB doesn't already have a seeded job — check `tests/integration/conftest.py` for an existing job-seeding helper before hand-rolling one.

- [ ] **Step 1.7: Run to verify it fails**

Run: `pytest tests/integration/test_matching_skill_coverage.py -v`
Expected: FAIL — `column "skill_coverage" does not exist` (before Step 1.5 migration is applied to the test DB) or a `KeyError`/`None` mismatch (after) since `run_matching` doesn't compute it yet.

- [ ] **Step 1.8: Wire it into `run_matching`**

In `jobos/matcher/pipeline.py`, add near the top:

```python
from jobos.matcher.scorer import compute_requirement_match
```

Add a helper:

```python
def _skills_from_bullets(bullets: list[dict[str, Any]]) -> list[str]:
    """Every distinct word/phrase in bullet text — a coarse but real skill
    surface, since there is no dedicated skills table yet (see the matching
    relevance plan's Step 1 note on job_requirements being unwritten schema
    for the same underlying reason: no extraction step existed)."""
    text = " ".join(b.get("bullet_text") or "" for b in bullets)
    return [w.strip(",.():;") for w in text.split() if w.strip(",.():;")]
```

Inside `run_matching`'s job loop, after `tier = classify_tier(...)`:

```python
        hard_reqs_raw = await conn.fetchval(
            "SELECT hard_reqs FROM job_requirements WHERE job_id = $1", job["id"]
        )
        hard_reqs = json.loads(hard_reqs_raw) if hard_reqs_raw else []
        candidate_skills = _skills_from_bullets(bullets)
        coverage, missing = compute_requirement_match(hard_reqs, candidate_skills)
```

And extend the `INSERT ... ON CONFLICT` to also set `skill_coverage`/`missing_skills` (add `$6, $7` params and `json.dumps(missing)`). Add `import json` at the top if not already present.

- [ ] **Step 1.9: Run to verify it passes**

Run: `pytest tests/integration/test_matching_skill_coverage.py -v`
Expected: PASS

- [ ] **Step 1.10: Wire extraction into ingestion**

In `jobos/ingestion/poller.py`, after a job row is inserted (find the existing insert, likely returns the new job's id), add a call:

```python
from jobos.ingestion.requirement_extractor import extract_hard_requirements
...
hard_reqs = await extract_hard_requirements(job_description, settings)
if hard_reqs:
    await conn.execute(
        "INSERT INTO job_requirements (job_id, hard_reqs) VALUES ($1, $2::jsonb) "
        "ON CONFLICT (job_id) DO UPDATE SET hard_reqs = EXCLUDED.hard_reqs",
        job_id, json.dumps(hard_reqs),
    )
```

Match this exactly to the real insert-and-loop shape already in `poller.py` — read the file first, this plan doesn't have its exact current line numbers memorized correctly enough to blind-paste against.

- [ ] **Step 1.11: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: all passing, no regressions (baseline 408 as of this plan's writing).

- [ ] **Step 1.12: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add jobos/ingestion/requirement_extractor.py jobos/ingestion/poller.py jobos/matcher/pipeline.py alembic/versions/ tests/unit/test_requirement_extractor.py tests/integration/test_matching_skill_coverage.py
git commit -m "feat: extract hard job requirements and score skill-gap coverage

job_requirements.hard_reqs has existed since the first migration
with zero writers — nothing ever populated it, so the already-built
and tested compute_requirement_match() scored nothing real. Adds
the missing extraction step and wires it into run_matching, so
matches.missing_skills can tell a candidate what they're actually
missing instead of just a similarity number."
```

---

### Task 2: Warm-connection strength shapes tiering, not just post-hoc race eligibility

**Files:**
- Modify: `jobos/matcher/tier_gate.py` (`classify_tier`: drop `company_tier`, add `has_warm_contact`)
- Modify: `jobos/matcher/pipeline.py` (`run_matching`: compute warm contacts once, pass per-job)
- Test: `tests/unit/test_tier_gate.py` (extend or create)
- Test: `tests/integration/test_matching_warm_tiering.py`

**Interfaces:**
- Consumes: `jobos.referral.network_mapper.map_existing_network(user_contacts: list[dict], target_companies: list[str]) -> list[dict]` (existing, unchanged) — each returned dict has `matched_target_company` and `email` keys.
- Produces: `classify_tier(match_score: float, ev_score: float, has_warm_contact: bool = False) -> int` — **breaking signature change**, `company_tier` param removed. Find and update every call site (`grep -rn "classify_tier" jobos/ tests/` first).

- [ ] **Step 2.1: Write the failing tier-gate tests**

```python
# tests/unit/test_tier_gate.py — add these; keep any existing tests in the file
from jobos.matcher.tier_gate import classify_tier


def test_warm_contact_lowers_the_tier_1_bar():
    # Below the no-contact bar (needs 0.65/0.60) but above the warm-contact bar (0.50/0.40)
    assert classify_tier(match_score=0.55, ev_score=0.45, has_warm_contact=True) == 1


def test_no_warm_contact_uses_the_standard_bar():
    assert classify_tier(match_score=0.55, ev_score=0.45, has_warm_contact=False) == 2


def test_company_tier_param_no_longer_accepted():
    import inspect
    sig = inspect.signature(classify_tier)
    assert "company_tier" not in sig.parameters
```

- [ ] **Step 2.2: Run to verify failure**

Run: `pytest tests/unit/test_tier_gate.py -v`
Expected: FAIL — `test_warm_contact_lowers_the_tier_1_bar` fails (returns 2, not 1; `has_warm_contact` not accepted yet).

- [ ] **Step 2.3: Implement**

```python
# jobos/matcher/tier_gate.py
def classify_tier(match_score: float, ev_score: float, has_warm_contact: bool = False) -> int:
    """
    Tier 1 (triggers the 7-day warm-path race): match_score >= 0.65 and
    ev_score >= 0.60 OR, when a real warm connection exists at the company,
    the lower bar match_score >= 0.50 and ev_score >= 0.40 — referred
    applicants convert at 4-10x cold applies, so a real connection is worth
    more than marginal comp/similarity headroom (see docs/superpowers/plans/
    2026-08-12-matching-relevance-fixes.md for the evidence this is based on).
    Tier 2: match_score >= 0.50 (no warm path). Tier 3: everything else.
    """
    if has_warm_contact and match_score >= 0.50 and ev_score >= 0.40:
        tier = 1
    elif match_score >= 0.65 and ev_score >= 0.60:
        tier = 1
    elif match_score >= 0.50:
        tier = 2
    else:
        tier = 3

    logger.debug(
        "classified_job_tier",
        match_score=match_score, ev_score=ev_score,
        has_warm_contact=has_warm_contact, assigned_tier=tier,
    )
    return tier
```

- [ ] **Step 2.4: Run to verify it passes**

Run: `pytest tests/unit/test_tier_gate.py -v`
Expected: PASS

- [ ] **Step 2.5: Find and fix every other call site**

Run: `grep -rn "classify_tier(" jobos/ tests/` — update every call passing `company_tier=` to either drop it or pass `has_warm_contact=` instead, per call site's actual intent. `jobos/matcher/pipeline.py` is handled in the next step; check for any others (dashboard-facing code, other tests).

- [ ] **Step 2.6: Write the failing integration test**

```python
# tests/integration/test_matching_warm_tiering.py
import pytest

from jobos.matcher.pipeline import run_matching

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people")
    yield
    await tenant_a_conn.execute("DELETE FROM matches")
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people")


async def test_warm_contact_pulls_a_marginal_job_into_tier_1(tenant_a_conn, tenant_a_id):
    await tenant_a_conn.execute(
        "INSERT INTO cg_bullets (id, user_id, company, role, bullet_text, verification_status) "
        "VALUES (gen_random_uuid(), $1::uuid, 'Acme', 'Engineer', 'Built things', 'verified')",
        tenant_a_id,
    )
    job = await tenant_a_conn.fetchrow(
        "SELECT j.id, c.name AS company_name FROM jobs j JOIN companies c ON c.id = j.company_id LIMIT 1"
    )
    if job is None:
        pytest.skip("no seeded job+company available in this fixture DB")

    await tenant_a_conn.execute(
        "INSERT INTO people (id, user_id, full_name, company_domain, email, title, source) "
        "VALUES (gen_random_uuid(), $1::uuid, 'Warm Contact', $2, 'warm@example.com', 'Engineer', 'linkedin_connection')",
        tenant_a_id, job["company_name"],
    )

    await run_matching(tenant_a_conn, str(tenant_a_id))

    row = await tenant_a_conn.fetchrow(
        "SELECT tier FROM matches WHERE user_id = $1::uuid AND job_id = $2", tenant_a_id, job["id"]
    )
    assert row is not None
    # Exact tier depends on this job's real embedding similarity in the
    # fixture DB — assert has_warm_contact was at least considered by
    # checking tier is 1 or 2, never silently unaffected by contact presence.
    # Tighten this once the fixture DB has a controlled, known-similarity job.
```

Note: this test's final assertion is intentionally soft — read the actual fixture DB's job/embedding setup before finalizing it into a hard `== 1` assertion; don't force a brittle assertion against data this plan doesn't control precisely.

- [ ] **Step 2.7: Run to verify it fails or needs adjustment**

Run: `pytest tests/integration/test_matching_warm_tiering.py -v`
Confirm it fails because `run_matching` doesn't compute `has_warm_contact` yet (not because of a fixture-data issue — fix the fixture first if so).

- [ ] **Step 2.8: Wire warm-contact detection into `run_matching`**

In `jobos/matcher/pipeline.py`, add imports:

```python
from jobos.referral.network_mapper import map_existing_network
```

Before the job loop, after `jobs = await conn.fetch(...)`, change the jobs query to also select the company name (join `companies`), then:

```python
    contacts = [
        dict(row)
        for row in await conn.fetch(
            "SELECT full_name, company_domain, email, title, source FROM people WHERE user_id = $1::uuid",
            user_id,
        )
    ]
    company_names = list({j["company_name"] for j in jobs if j["company_name"]})
    warm_leads = await map_existing_network(
        [{**c, "company": c["company_domain"]} for c in contacts], company_names
    ) if contacts and company_names else []
    warm_companies = {w["matched_target_company"] for w in warm_leads if w.get("email")}
```

In the loop, change:

```python
        tier = classify_tier(match_score=score, ev_score=ev_score)
```

to:

```python
        tier = classify_tier(
            match_score=score, ev_score=ev_score,
            has_warm_contact=job["company_name"] in warm_companies,
        )
```

(Adjust the jobs `SELECT` to alias the joined company name as `company_name` — check the exact join needed against `companies` in the existing query shape.)

- [ ] **Step 2.9: Run to verify it passes**

Run: `pytest tests/integration/test_matching_warm_tiering.py tests/unit/test_tier_gate.py -v`
Expected: PASS

- [ ] **Step 2.10: Run the full suite**

Run: `python -m pytest tests/ -q`
Expected: all passing, no regressions.

- [ ] **Step 2.11: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add jobos/matcher/tier_gate.py jobos/matcher/pipeline.py tests/unit/test_tier_gate.py tests/integration/test_matching_warm_tiering.py
git commit -m "feat: let warm-connection strength pull a job into Tier 1

classify_tier's company_tier param was accepted and never read —
removed. Replaced with has_warm_contact, computed once per matching
run via the existing map_existing_network (pure in-memory, no new
I/O). Referrals convert 4-10x better than cold applies but
previously only affected outreach after a job already hit Tier 1
on comp+similarity alone; a marginal-but-warm job never got
reconsidered. Now it can clear Tier 1 at a lower match/EV bar when
a real connection exists at that company."
```

## Self-Review Notes

- **Spec coverage:** both fixes from the audit are covered (skill-gap scoring, warm-connection tiering). The third finding (dead `company_tier` param) is folded into Step 2 rather than its own step, since removing it and adding `has_warm_contact` are the same signature edit — a separate step would just immediately conflict with itself.
- **Deferred, not in this plan:** replacing the arbitrary `P_OFFER_SCALE = 0.35` (needs real outcome-feedback data this system doesn't collect yet) and any culture/growth/flexibility signal (no data source decided). Both were explicitly deprioritized in the product-manager-toolkit pass this plan is based on.
- **Known soft spot:** Step 2.6's integration test has an intentionally weak final assertion pending a look at the real fixture DB's seeded job data — tighten it during implementation, don't ship it soft.
