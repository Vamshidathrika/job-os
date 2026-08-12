# Workflow Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 15 phase-named tabs in `dashboard/src/App.tsx` with a 6-section workflow sidebar (Profile & LinkedIn, Job Matches, Applications, Referrals, Interview Prep, Calendar & Integrations) plus a global "Needs your review" inbox, per `docs/superpowers/specs/2026-08-12-workflow-dashboard-design.md`.

**Architecture:** Backend gets 3 additive endpoints (list-pending / reject / LinkedIn-upload / resume-generate — 4 routes, grouped as 3 tasks) that wrap existing pipeline logic; no matching/tailoring/referral/cold-apply logic changes. Frontend splits the single 845-line `App.tsx` into a `Sidebar` + `TopBar` shell plus 7 page components, each receiving typed props from the state `App.tsx` already owns — no new state library.

**Tech Stack:** FastAPI/asyncpg/pytest (backend, unchanged), React + TypeScript + Vite, `lucide-react` icons (frontend, unchanged) — no new npm dependencies.

## Global Constraints

- Every new backend route uses the existing auth pattern verbatim: `tenant: str = Depends(authenticated_tenant)`, and `conn: Any = Depends(tenant_db)` unless the wrapped function manages its own `tenant_conn` (see Task 3).
- No fabricated data: an empty/unwired state renders as plain text saying so, never a placeholder number or fake "CONNECTED" status (established pattern, see `jobos/api/main.py` module docstring).
- No new npm dependencies. Reuse `lucide-react` icons and the CSS variables already defined in `dashboard/src/index.css`.
- Design direction: dense/quiet ops-tool tone. Drop `glass-panel` as the default for every panel and drop the 3-point radial-gradient body background; reserve gradient/glow accents for exactly two elements — the logo mark and the review-inbox badge count.
- Sidebar collapses to an icon-only rail below 900px viewport width.
- All tables/lists are scroll-contained (`overflow-x: auto` on their own wrapper), never page-overflowing.
- Backend: pytest integration tests for every new route, following `tests/integration/test_api_execute_action.py`'s exact fixture pattern (`tenant_a_conn`, `tenant_a_id`, `db_pool`, `httpx.ASGITransport`).
- Frontend: no test framework is wired into `dashboard/`. Verification is manual, via the `mcp__Claude_Browser__*` tools — screenshot + `read_page` after each frontend task.

---

### Task 1: Review-inbox read + reject on the action queue

**Files:**
- Modify: `jobos/action_queue/queue.py` (add two methods to `ActionQueue`)
- Modify: `jobos/api/main.py:271-274` (extend `list_actions`), add new route after line 315
- Test: `tests/unit/test_action_queue.py` (create if it doesn't exist — check first with `ls tests/unit/test_action_queue.py`)
- Test: `tests/integration/test_api_execute_action.py` (append)

**Interfaces:**
- Produces: `ActionQueue.list_pending(self, limit: int = 50) -> list[dict[str, Any]]` — read-only, does **not** claim rows (must not call `dequeue_batch`, which sets `status='processing'` as a side effect — a pending-review listing must be idempotent).
- Produces: `ActionQueue.mark_rejected(self, action_id: str) -> None`
- Produces route: `GET /api/actions?status=pending` (existing `band` param path unchanged for `status` unset)
- Produces route: `POST /api/actions/{action_id}/reject`

- [ ] **Step 1: Write the failing unit tests for the two new queue methods**

Check if `tests/unit/test_action_queue.py` exists; if not, create it. Add:

```python
"""Unit tests for ActionQueue.list_pending and mark_rejected."""

import pytest

from jobos.action_queue.queue import ActionQueue

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn):
    await tenant_a_conn.execute("DELETE FROM action_queue")
    yield
    await tenant_a_conn.execute("DELETE FROM action_queue")


async def test_list_pending_does_not_claim_rows(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")

    pending = await queue.list_pending()

    assert [p["action_id"] for p in pending] == [action_id]
    status = await tenant_a_conn.fetchval(
        "SELECT status FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert status == "pending"  # unchanged — list_pending must not claim


async def test_list_pending_spans_bands_and_types(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")
    await queue.enqueue("submit_application", {"job_url": "x"}, band="B")

    pending = await queue.list_pending()

    assert {p["action_type"] for p in pending} == {"referral_touch", "submit_application"}


async def test_mark_rejected_sets_status(tenant_a_conn, tenant_a_id):
    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")

    await queue.mark_rejected(action_id)

    status = await tenant_a_conn.fetchval(
        "SELECT status FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert status == "rejected"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_action_queue.py -v`
Expected: FAIL with `AttributeError: 'ActionQueue' object has no attribute 'list_pending'`

- [ ] **Step 3: Implement the two methods**

In `jobos/action_queue/queue.py`, add after `escalate` (before `count_actions_since`):

```python
    async def list_pending(self, limit: int = 50) -> list[dict[str, Any]]:
        """Read-only listing of every pending action, any band or type.

        Unlike dequeue_batch, this never claims rows (no UPDATE) — it backs
        a review inbox a human just looks at, and looking must not change
        what a worker later picks up.
        """
        rows = await self.conn.fetch(
            """
            SELECT id, action_type, payload, band, status, created_at
            FROM action_queue
            WHERE status = 'pending'
            ORDER BY created_at
            LIMIT $1
            """,
            limit,
        )
        return [
            {
                "action_id": str(row["id"]),
                "action_type": row["action_type"],
                "payload": json.loads(row["payload"]),
                "band": row["band"],
                "status": row["status"],
                "tenant_id": self.tenant_id,
            }
            for row in rows
        ]

    async def mark_rejected(self, action_id: str) -> None:
        """A human declined this action. It must never be picked up again."""
        await self.conn.execute(
            """
            UPDATE action_queue
            SET status = 'rejected', updated_at = now()
            WHERE id = $1
            """,
            uuid.UUID(action_id),
        )
        logger.info("action_rejected", action_id=action_id)
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `pytest tests/unit/test_action_queue.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Write the failing API integration tests**

Append to `tests/integration/test_api_execute_action.py`:

```python
async def test_list_pending_actions_across_bands(tenant_a_conn, tenant_a_id, db_pool):
    from jobos.action_queue.queue import ActionQueue

    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")
    await queue.enqueue("submit_application", {"job_url": FIXTURE_URL}, band="B")

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.get(
            "/api/actions?status=pending", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {a["action_type"] for a in body} == {"referral_touch", "submit_application"}


async def test_reject_action_marks_rejected_and_leaves_it_unexecuted(
    tenant_a_conn, tenant_a_id, db_pool
):
    from jobos.action_queue.queue import ActionQueue

    queue = ActionQueue(conn=tenant_a_conn, tenant_id=str(tenant_a_id))
    action_id = await queue.enqueue("referral_touch", {"to": "a@b.com"}, band="A")

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.post(
            f"/api/actions/{action_id}/reject", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    assert response.json() == {"action_id": action_id, "status": "rejected"}
    row = await tenant_a_conn.fetchrow(
        "SELECT status FROM action_queue WHERE id = $1::uuid", action_id
    )
    assert row["status"] == "rejected"
```

- [ ] **Step 6: Run integration tests to verify they fail**

Run: `pytest tests/integration/test_api_execute_action.py -v -k "pending or reject"`
Expected: FAIL (404 — routes don't exist yet)

- [ ] **Step 7: Implement the routes**

In `jobos/api/main.py`, replace the existing `list_actions` (lines 271-274) with:

```python
@app.get("/api/actions")
async def list_actions(
    band: str = "A",
    status: str | None = None,
    tenant: str = Depends(authenticated_tenant),
    conn: Any = Depends(tenant_db),
) -> list[dict[str, Any]]:
    queue = ActionQueue(conn=conn, tenant_id=tenant)
    if status == "pending":
        return await queue.list_pending(limit=50)
    return await queue.dequeue_batch(band=band, limit=20)
```

Then add a new route directly after `execute_action` (after line 315):

```python
@app.post("/api/actions/{action_id}/reject")
async def reject_action(
    action_id: str, tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)
) -> dict[str, Any]:
    """A human declined this from the review inbox — mark it rejected without
    running its handler. Symmetric with execute_action's approve path."""
    row = await conn.fetchrow("SELECT id FROM action_queue WHERE id = $1::uuid", action_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No action {action_id!r}")

    queue = ActionQueue(conn=conn, tenant_id=tenant)
    await queue.mark_rejected(action_id=action_id)
    return {"action_id": action_id, "status": "rejected"}
```

- [ ] **Step 8: Run integration tests to verify they pass**

Run: `pytest tests/integration/test_api_execute_action.py tests/unit/test_action_queue.py -v`
Expected: PASS (all tests, including the 3 pre-existing ones in `test_api_execute_action.py`)

- [ ] **Step 9: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add jobos/action_queue/queue.py jobos/api/main.py tests/unit/test_action_queue.py tests/integration/test_api_execute_action.py
git commit -m "feat(api): review-inbox read + reject on the action queue

GET /api/actions?status=pending lists every pending action across
bands/types read-only (list_pending never claims rows, unlike
dequeue_batch). POST /api/actions/{id}/reject marks an action
rejected without running its handler — symmetric with the existing
approve/execute path."
```

---

### Task 2: LinkedIn export upload endpoint

**Files:**
- Modify: `jobos/api/main.py` (add imports + one route)
- Test: `tests/integration/test_linkedin_upload_endpoint.py` (create)

**Interfaces:**
- Consumes: `jobos.onboarding.linkedin_import.import_profile(conn, user_id, zip_path=None, resume_path=None) -> dict[str, int]` (existing, returns `{"bullets": int, "connections": int, "skills": int}`)
- Produces route: `POST /api/onboarding/linkedin-import` (multipart form, field name `file`)

- [ ] **Step 1: Find a real LinkedIn export fixture**

Run: `find tests -iname "*linkedin*" -name "*.zip"`

This session's earlier work built a realistic test fixture for the LinkedIn importer CLI path — reuse it. If none is found, check `tests/fixtures/` and `tests/integration/test_linkedin_import.py` (or similarly named) for how existing importer tests build their zip, and reuse that same fixture-building helper.

- [ ] **Step 2: Write the failing test**

Create `tests/integration/test_linkedin_upload_endpoint.py` (adjust the fixture-path import to match what Step 1 found):

```python
"""Integration test for POST /api/onboarding/linkedin-import."""

from pathlib import Path

import httpx
import pytest

from jobos.api import main as api_main
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

# Adjust this path to the real fixture found in Step 1.
FIXTURE_ZIP = Path(__file__).resolve().parents[1] / "fixtures" / "linkedin_export.zip"


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people WHERE source = 'linkedin_connection'")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    api_main.app.state.pool = db_pool
    yield
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM people WHERE source = 'linkedin_connection'")
    await tenant_a_conn.execute("DELETE FROM api_tokens")


async def test_uploaded_zip_is_imported_and_summary_returned(tenant_a_conn, tenant_a_id, db_pool):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")

    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with open(FIXTURE_ZIP, "rb") as f:
            response = await client.post(
                "/api/onboarding/linkedin-import",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("linkedin_export.zip", f, "application/zip")},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["bullets"] > 0

    stored = await tenant_a_conn.fetchval("SELECT count(*) FROM cg_bullets")
    assert stored == body["bullets"]


async def test_upload_without_a_file_is_rejected(tenant_a_conn, tenant_a_id, db_pool):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")

    transport = httpx.ASGITransport(app=api_main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/onboarding/linkedin-import",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/integration/test_linkedin_upload_endpoint.py -v`
Expected: FAIL with 404 (route doesn't exist)

- [ ] **Step 4: Implement the route**

In `jobos/api/main.py`, add to the imports (near the top, with the other `fastapi` import):

```python
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
```

Add near the other `jobos.onboarding` imports:

```python
from jobos.onboarding.linkedin_import import import_profile
```

Add the route after `career_graph_summary` (after line 359):

```python
@app.post("/api/onboarding/linkedin-import")
async def upload_linkedin_export(
    file: UploadFile = File(...),
    tenant: str = Depends(authenticated_tenant),
    conn: Any = Depends(tenant_db),
) -> dict[str, int]:
    """HTTP wrapper around the existing CLI-only LinkedIn import path — no
    new parsing logic, just an upload handle in front of import_profile."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        return await import_profile(conn, tenant, zip_path=tmp_path)
    finally:
        import os

        os.unlink(tmp_path)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/integration/test_linkedin_upload_endpoint.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add jobos/api/main.py tests/integration/test_linkedin_upload_endpoint.py
git commit -m "feat(api): HTTP upload endpoint for the LinkedIn export

POST /api/onboarding/linkedin-import wraps the existing CLI-only
import_profile() behind a multipart upload, so the dashboard can
run the profile setup step without a terminal."
```

---

### Task 3: Resume-generation endpoint

**Files:**
- Modify: `jobos/api/main.py` (add imports + one route)
- Test: `tests/integration/test_generate_resume_endpoint.py` (create)

**Interfaces:**
- Consumes: `jobos.runner.pipeline.stage_upload_resume(pool, user_id, job_id, settings) -> dict[str, str]` (existing; raises `NoJobFoundError`, `NoVerifiedBulletsError`, or `jobos.composio_client.client.ComposioActionError`)
- Produces route: `POST /api/jobs/{job_id}/generate-resume`

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_generate_resume_endpoint.py`:

```python
"""Integration test for POST /api/jobs/{job_id}/generate-resume."""

import httpx
import pytest

from jobos.api import main as api_main
from jobos.vault.api_tokens import create_token

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(tenant_a_conn, db_pool):
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM jobs")
    await tenant_a_conn.execute("DELETE FROM api_tokens")
    api_main.app.state.pool = db_pool
    yield
    await tenant_a_conn.execute("DELETE FROM cg_bullets")
    await tenant_a_conn.execute("DELETE FROM jobs")
    await tenant_a_conn.execute("DELETE FROM api_tokens")


async def _client_and_token(db_pool, tenant_a_id):
    async with db_pool.acquire() as conn:
        token = await create_token(conn, str(tenant_a_id), name="test")
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test"), token


async def test_generate_resume_for_unknown_job_returns_404(tenant_a_conn, tenant_a_id, db_pool):
    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.post(
            "/api/jobs/00000000-0000-0000-0000-000000000099/generate-resume",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 404


async def test_generate_resume_with_no_verified_bullets_returns_422(
    tenant_a_conn, tenant_a_id, db_pool
):
    job_id = await tenant_a_conn.fetchval(
        """
        INSERT INTO companies (id, name) VALUES (gen_random_uuid(), 'Acme') RETURNING id
        """
    )
    job_id = await tenant_a_conn.fetchval(
        """
        INSERT INTO jobs (id, company_id, title, description, source, external_id)
        VALUES (gen_random_uuid(), $1, 'Engineer', 'Build things', 'greenhouse', 'ext-1')
        RETURNING id
        """,
        job_id,
    )

    client, token = await _client_and_token(db_pool, tenant_a_id)
    async with client:
        response = await client.post(
            f"/api/jobs/{job_id}/generate-resume",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 422
```

Note: check `jobs` and `companies` table columns with `\d jobs` / `\d companies` in psql before running — adjust the INSERT columns in the second test if they don't match (this repo's schema may require additional NOT NULL columns; add whatever the migration requires).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_generate_resume_endpoint.py -v`
Expected: FAIL with 404 for both (route doesn't exist — first test's 404 is coincidentally the right status but for the wrong reason; verify by checking the response body has no `detail` mentioning "No job")

- [ ] **Step 3: Implement the route**

In `jobos/api/main.py`, add to imports:

```python
from jobos.runner.pipeline import NoJobFoundError, NoVerifiedBulletsError, stage_upload_resume
from jobos.composio_client.client import ComposioActionError
```

Add the route after the new `reject_action` route from Task 1:

```python
@app.post("/api/jobs/{job_id}/generate-resume")
async def generate_resume(
    job_id: str, tenant: str = Depends(authenticated_tenant)
) -> dict[str, str]:
    """Thin wrapper around stage_upload_resume — no new tailoring logic.
    Uses the pool directly (not the per-request tenant_db connection):
    stage_upload_resume opens its own tenant-scoped connection internally."""
    try:
        return await stage_upload_resume(app.state.pool, tenant, job_id, settings)
    except NoJobFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except NoVerifiedBulletsError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ComposioActionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_generate_resume_endpoint.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add jobos/api/main.py tests/integration/test_generate_resume_endpoint.py
git commit -m "feat(api): resume-generation endpoint for the Job Matches page

POST /api/jobs/{id}/generate-resume wraps the existing
stage_upload_resume pipeline stage in HTTP so the dashboard can
trigger tailoring + Drive upload for one job without the CLI."
```

---

### Task 4: Shared frontend types and API helper

**Files:**
- Create: `dashboard/src/types.ts`
- Create: `dashboard/src/api.ts`

**Interfaces:**
- Produces: `types.ts` exports `PipelineStats`, `SecurityStatus`, `Job`, `ActionItem` interfaces
- Produces: `api.ts` exports `authFetch<T>(path: string, token: string, opts?: RequestInit) => Promise<T | null>`

- [ ] **Step 1: Create the types module**

Create `dashboard/src/types.ts`:

```typescript
export interface PipelineStats {
  jobs_tracked: number;
  applications_sent: number;
  interviews_scheduled: number;
  offers_received: number;
  response_rate: number;
  avg_days_to_interview: number;
}

export interface SecurityStatus {
  tenant_id: string;
  rls_enforced: boolean;
  policy_prohibitions_count: number;
  prohibitions: string[];
  circuit_breaker: {
    action_counts: { applies: number; emails: number };
    limits: { applies: number; emails: number };
  };
  kms_vault_status: string;
}

export interface Job {
  title: string;
  company: string;
  location: string;
  tier: number | null;
  ev_score: number | null;
  match_score: number | null;
  [key: string]: unknown;
}

export interface ActionItem {
  action_id: string;
  action_type: string;
  band: string;
  status: string;
  payload: Record<string, unknown>;
}
```

- [ ] **Step 2: Create the API helper**

Create `dashboard/src/api.ts`:

```typescript
export async function authFetch<T>(
  path: string,
  token: string,
  opts: RequestInit = {}
): Promise<T | null> {
  const res = await fetch(path, {
    ...opts,
    headers: { ...opts.headers, Authorization: `Bearer ${token}` },
  });
  if (!res.ok) return null;
  return res.json();
}
```

- [ ] **Step 3: Verify it compiles**

Run: `cd dashboard && npx tsc --noEmit`
Expected: no new errors (these two files aren't imported anywhere yet, so this just confirms syntax)

- [ ] **Step 4: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add dashboard/src/types.ts dashboard/src/api.ts
git commit -m "refactor(dashboard): extract shared types and a fetch helper

Pulled the interfaces and the repeated fetch-with-auth-header
pattern out of App.tsx ahead of splitting it into page components —
every new page needs both."
```

---

### Task 5: Sidebar + TopBar shell and design-direction CSS

**Files:**
- Create: `dashboard/src/components/Sidebar.tsx`
- Create: `dashboard/src/components/TopBar.tsx`
- Modify: `dashboard/src/index.css`

**Interfaces:**
- Produces: `Sidebar` props `{ activeSection: string; onSelect: (id: string) => void; pendingCount: number }`. Section ids: `'profile' | 'matches' | 'applications' | 'referrals' | 'interview-prep' | 'calendar'`.
- Produces: `TopBar` props `{ onSync: () => void; syncing: boolean; shadowModeReal: boolean | null; onToggleShadowMode: () => void; onSignOut: () => void; pendingCount: number; onOpenInbox: () => void }`.

- [ ] **Step 1: Update index.css for the design direction**

In `dashboard/src/index.css`, replace the `body` rule's `background-image` (currently the 3-point radial gradient wash) with a flatter one, and add sidebar styles. Replace:

```css
body {
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-body);
  min-height: 100vh;
  overflow-x: hidden;
  background-image: 
    radial-gradient(at 10% 10%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
    radial-gradient(at 90% 90%, rgba(168, 85, 247, 0.1) 0px, transparent 50%),
    radial-gradient(at 50% 50%, rgba(6, 182, 212, 0.08) 0px, transparent 50%);
  background-attachment: fixed;
}
```

with:

```css
body {
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-body);
  min-height: 100vh;
  overflow-x: hidden;
}
```

Then append at the end of the file:

```css
/* App shell: sidebar + content */
.app-shell {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 240px;
  flex-shrink: 0;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  padding: 20px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sidebar .nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-weight: 500;
  text-align: left;
  width: 100%;
}

.sidebar .nav-item.active {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-primary);
  font-weight: 600;
}

.sidebar .nav-item:hover {
  color: var(--text-primary);
}

.sidebar .nav-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-content {
  flex: 1;
  min-width: 0;
  padding: 24px;
}

.scroll-x {
  overflow-x: auto;
}

@media (max-width: 900px) {
  .sidebar {
    width: 64px;
  }
  .sidebar .nav-label {
    display: none;
  }
}
```

- [ ] **Step 2: Create the Sidebar component**

Create `dashboard/src/components/Sidebar.tsx`:

```tsx
import { User, Target, Send, Users, Calendar, Settings } from 'lucide-react';

const SECTIONS = [
  { id: 'profile', label: 'Profile & LinkedIn', icon: User },
  { id: 'matches', label: 'Job Matches', icon: Target },
  { id: 'applications', label: 'Applications', icon: Send },
  { id: 'referrals', label: 'Referrals', icon: Users },
  { id: 'interview-prep', label: 'Interview Prep', icon: Calendar },
  { id: 'calendar', label: 'Calendar & Integrations', icon: Settings },
];

interface SidebarProps {
  activeSection: string;
  onSelect: (id: string) => void;
}

export function Sidebar({ activeSection, onSelect }: SidebarProps) {
  return (
    <nav className="sidebar">
      {SECTIONS.map((s) => {
        const Icon = s.icon;
        const isActive = activeSection === s.id;
        return (
          <button
            key={s.id}
            className={`nav-item${isActive ? ' active' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <Icon size={18} />
            <span className="nav-label">{s.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 3: Create the TopBar component**

Create `dashboard/src/components/TopBar.tsx`:

```tsx
import { Cpu, RefreshCw, Eye, Zap, Bell } from 'lucide-react';

interface TopBarProps {
  onSync: () => void;
  syncing: boolean;
  shadowModeReal: boolean | null;
  onToggleShadowMode: () => void;
  onSignOut: () => void;
  pendingCount: number;
  onOpenInbox: () => void;
}

export function TopBar({
  onSync,
  syncing,
  shadowModeReal,
  onToggleShadowMode,
  onSignOut,
  pendingCount,
  onOpenInbox,
}: TopBarProps) {
  return (
    <header
      style={{
        padding: '16px 24px',
        marginBottom: '24px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderBottom: '1px solid var(--border-color)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div
          style={{
            background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
            padding: '10px',
            borderRadius: '12px',
            display: 'flex',
          }}
        >
          <Cpu size={22} color="#fff" />
        </div>
        <h1 style={{ fontSize: '1.2rem' }}>JOBOS</h1>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <button
          onClick={onOpenInbox}
          style={{
            position: 'relative',
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid var(--border-color)',
            padding: '8px 14px',
            borderRadius: '8px',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.8rem',
          }}
        >
          <Bell size={14} />
          Needs your review
          {pendingCount > 0 && (
            <span
              style={{
                background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
                color: '#fff',
                borderRadius: '9999px',
                fontSize: '0.7rem',
                fontWeight: 700,
                padding: '1px 7px',
              }}
            >
              {pendingCount}
            </span>
          )}
        </button>

        <button
          onClick={onSync}
          style={{
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid var(--border-color)',
            padding: '8px 14px',
            borderRadius: '8px',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.8rem',
          }}
        >
          <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
          Sync
        </button>

        <button
          onClick={onToggleShadowMode}
          disabled={shadowModeReal === null}
          title="Toggles tenants.autonomy_mode for real — this changes what the send-guard actually allows."
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            borderRadius: '10px',
            border:
              shadowModeReal === null
                ? '1px solid var(--border-color)'
                : shadowModeReal
                ? '1px solid rgba(245, 158, 11, 0.4)'
                : '1px solid rgba(16, 185, 129, 0.4)',
            background:
              shadowModeReal === null
                ? 'rgba(255,255,255,0.03)'
                : shadowModeReal
                ? 'rgba(245, 158, 11, 0.15)'
                : 'rgba(16, 185, 129, 0.15)',
            color: shadowModeReal === null ? 'var(--text-muted)' : shadowModeReal ? '#fbbf24' : '#34d399',
            fontWeight: 600,
            fontSize: '0.8rem',
          }}
        >
          {shadowModeReal !== false ? <Eye size={16} /> : <Zap size={16} />}
          {shadowModeReal === null ? 'Loading…' : shadowModeReal ? 'Shadow mode' : 'Autopilot live'}
        </button>

        <button
          onClick={onSignOut}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
            fontSize: '0.8rem',
            textDecoration: 'underline',
          }}
        >
          sign out
        </button>
      </div>
    </header>
  );
}
```

- [ ] **Step 4: Verify it compiles**

Run: `cd dashboard && npx tsc --noEmit`
Expected: no errors (components aren't wired into App.tsx yet, this checks syntax only)

- [ ] **Step 5: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add dashboard/src/components/Sidebar.tsx dashboard/src/components/TopBar.tsx dashboard/src/index.css
git commit -m "feat(dashboard): sidebar + top bar shell, quiet-tone CSS

Replaces the 15-tab phase grid's container chrome. Design direction:
drop the glass-panel-everywhere + 3-point gradient wash, reserve
gradient/glow for the logo and the review-inbox badge count only.
Sidebar collapses to an icon rail under 900px."
```

---

### Task 6: Review Inbox page

**Files:**
- Create: `dashboard/src/pages/ReviewInboxPage.tsx`

**Interfaces:**
- Consumes: `ActionItem` from `../types`, `authFetch` from `../api`
- Produces: `ReviewInboxPage` props `{ token: string; pending: ActionItem[]; onActed: (actionId: string) => void }` — `onActed` removes the item from parent state after approve/reject.

- [ ] **Step 1: Create the page**

Create `dashboard/src/pages/ReviewInboxPage.tsx`:

```tsx
import { useState } from 'react';
import { authFetch } from '../api';
import type { ActionItem } from '../types';

interface ReviewInboxPageProps {
  token: string;
  pending: ActionItem[];
  onActed: (actionId: string) => void;
}

export function ReviewInboxPage({ token, pending, onActed }: ReviewInboxPageProps) {
  const [busyId, setBusyId] = useState<string | null>(null);

  const act = async (actionId: string, verb: 'execute' | 'reject') => {
    setBusyId(actionId);
    try {
      await authFetch(`/api/actions/${actionId}/${verb}`, token, { method: 'POST' });
      onActed(actionId);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Needs your review</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '16px' }}>
        Every send, apply, or schedule action stops here first. Nothing runs until you approve it.
      </p>
      {pending.length === 0 ? (
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Nothing pending.</span>
      ) : (
        <div className="scroll-x" style={{ display: 'grid', gap: '10px' }}>
          {pending.map((item) => (
            <div
              key={item.action_id}
              style={{
                padding: '14px',
                background: 'rgba(255,255,255,0.03)',
                borderRadius: '10px',
                border: '1px solid var(--border-color)',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: '12px',
              }}
            >
              <div>
                <strong style={{ fontSize: '0.9rem' }}>{item.action_type}</strong>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                  Band {item.band}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                <button
                  onClick={() => act(item.action_id, 'reject')}
                  disabled={busyId === item.action_id}
                  style={{
                    background: 'rgba(244, 63, 94, 0.15)',
                    color: '#f87171',
                    border: '1px solid rgba(244, 63, 94, 0.3)',
                    padding: '6px 14px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  Reject
                </button>
                <button
                  onClick={() => act(item.action_id, 'execute')}
                  disabled={busyId === item.action_id}
                  style={{
                    background: 'var(--accent-emerald)',
                    color: '#fff',
                    border: 'none',
                    padding: '6px 14px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  {busyId === item.action_id ? 'Working…' : 'Approve'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd dashboard && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add dashboard/src/pages/ReviewInboxPage.tsx
git commit -m "feat(dashboard): review inbox page — approve/reject in one place

Replaces having to check each section for pending items. Backed by
GET /api/actions?status=pending and the new reject endpoint from
this session's backend work."
```

---

### Task 7: Job Matches page with resume generation

**Files:**
- Create: `dashboard/src/pages/JobMatchesPage.tsx`

**Interfaces:**
- Consumes: `Job` from `../types`, `authFetch` from `../api`
- Produces: `JobMatchesPage` props `{ token: string; jobs: Job[] }`

- [ ] **Step 1: Create the page**

Create `dashboard/src/pages/JobMatchesPage.tsx`:

```tsx
import { useState } from 'react';
import { authFetch } from '../api';
import type { Job } from '../types';

interface JobMatchesPageProps {
  token: string;
  jobs: Job[];
}

export function JobMatchesPage({ token, jobs }: JobMatchesPageProps) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<{ web_view_link?: string; detail?: string } | null>(null);

  const scored = jobs.filter((j) => j.tier != null);

  const generateResume = async (job: Job) => {
    setGenerating(true);
    setResult(null);
    try {
      const res = await authFetch<{ web_view_link?: string }>(
        `/api/jobs/${job.id}/generate-resume`,
        token,
        { method: 'POST' }
      );
      setResult(res ?? { detail: 'Generation failed — see server logs.' });
    } finally {
      setGenerating(false);
    }
  };

  if (scored.length === 0) {
    return (
      <div>
        <h2 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Job Matches</h2>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          No jobs scored yet — run <code>jobos match</code>.
        </span>
      </div>
    );
  }

  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Job Matches</h2>
      <div className="scroll-x" style={{ display: 'grid', gap: '10px' }}>
        {scored.map((j, idx) => (
          <div
            key={idx}
            style={{
              padding: '14px',
              background: 'rgba(255,255,255,0.03)',
              borderRadius: '10px',
              border: '1px solid var(--border-color)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                cursor: 'pointer',
              }}
              onClick={() => setOpenIdx(openIdx === idx ? null : idx)}
            >
              <div>
                <strong style={{ fontSize: '1rem' }}>{j.title}</strong>
                <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {j.company} • {j.location}
                </div>
              </div>
              <span className="badge badge-band-a">
                Tier {j.tier} (EV ${j.ev_score?.toLocaleString()})
              </span>
            </div>
            {openIdx === idx && (
              <div style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--border-color)' }}>
                <button
                  onClick={() => generateResume(j)}
                  disabled={generating}
                  style={{
                    background: 'var(--accent-indigo)',
                    color: '#fff',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                  }}
                >
                  {generating ? 'Generating…' : 'Generate tailored resume'}
                </button>
                {result && (
                  <div style={{ marginTop: '10px', fontSize: '0.8rem' }}>
                    {result.web_view_link ? (
                      <a href={result.web_view_link} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-cyan)' }}>
                        Open in Drive
                      </a>
                    ) : (
                      <span style={{ color: '#f87171' }}>{result.detail}</span>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd dashboard && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add dashboard/src/pages/JobMatchesPage.tsx
git commit -m "feat(dashboard): Job Matches page with end-to-end resume generation

Click a job, generate a tailored resume, get the Drive link back —
the core MVP loop from the workflow-dashboard spec."
```

---

### Task 8: Profile & LinkedIn page

**Files:**
- Create: `dashboard/src/pages/ProfilePage.tsx`

**Interfaces:**
- Consumes: `authFetch` from `../api`
- Produces: `ProfilePage` props `{ token: string; careerGraph: { bullets_total: number; bullets_verified: number; linkedin_connections: number } | null; onImported: () => void }` — `onImported` triggers the parent's re-sync.

- [ ] **Step 1: Create the page**

Create `dashboard/src/pages/ProfilePage.tsx`:

```tsx
import { useRef, useState } from 'react';

interface ProfilePageProps {
  token: string;
  careerGraph: { bullets_total: number; bullets_verified: number; linkedin_connections: number } | null;
  onImported: () => void;
}

export function ProfilePage({ token, careerGraph, onImported }: ProfilePageProps) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError('');
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('/api/onboarding/linkedin-import', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      if (!res.ok) {
        setError(`Import failed (${res.status}).`);
        return;
      }
      onImported();
    } finally {
      setUploading(false);
    }
  };

  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '8px' }}>Profile & LinkedIn</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '16px' }}>
        Upload your LinkedIn data export (Settings → Data privacy → Get a copy of your data, on
        linkedin.com). Live LinkedIn login isn't supported — the export is the only source that
        doesn't risk your account.
      </p>

      <div
        style={{
          border: '1px dashed var(--border-color)',
          borderRadius: '10px',
          padding: '24px',
          textAlign: 'center',
          marginBottom: '20px',
        }}
      >
        <input
          ref={fileInput}
          type="file"
          accept=".zip"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleUpload(file);
          }}
        />
        <button
          onClick={() => fileInput.current?.click()}
          disabled={uploading}
          style={{
            background: 'var(--accent-indigo)',
            color: '#fff',
            border: 'none',
            padding: '10px 20px',
            borderRadius: '8px',
            fontWeight: 600,
            fontSize: '0.85rem',
          }}
        >
          {uploading ? 'Importing…' : 'Upload LinkedIn export (.zip)'}
        </button>
        {error && <p style={{ color: '#f87171', fontSize: '0.8rem', marginTop: '10px' }}>{error}</p>}
      </div>

      {careerGraph ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '10px' }}>
            <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{careerGraph.bullets_total}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Career Graph bullets</div>
          </div>
          <div style={{ background: 'rgba(16, 185, 129, 0.1)', padding: '14px', borderRadius: '10px' }}>
            <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#34d399' }}>
              {careerGraph.bullets_verified}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Verified (tailoring-eligible)</div>
          </div>
          <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px', borderRadius: '10px' }}>
            <div style={{ fontSize: '1.4rem', fontWeight: 700 }}>{careerGraph.linkedin_connections}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>LinkedIn connections imported</div>
          </div>
        </div>
      ) : (
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>No profile imported yet.</span>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd dashboard && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add dashboard/src/pages/ProfilePage.tsx
git commit -m "feat(dashboard): Profile & LinkedIn page with in-app export upload

Replaces the CLI-only jobos import --linkedin-zip step with a
drag-and-click upload backed by the new
POST /api/onboarding/linkedin-import endpoint."
```

---

### Task 9: Relocate Applications, Referrals, Interview Prep, Calendar & Integrations pages

**Files:**
- Create: `dashboard/src/pages/ApplicationsPage.tsx`
- Create: `dashboard/src/pages/ReferralsPage.tsx`
- Create: `dashboard/src/pages/InterviewPrepPage.tsx`
- Create: `dashboard/src/pages/CalendarIntegrationsPage.tsx`

These four are mechanical extractions of existing, working JSX out of `dashboard/src/App.tsx` — no new logic, no new backend calls. Copy the JSX body verbatim (adjusting only `style={{...}}` inline objects, which don't change) into a component that takes the same data as props instead of reading closure variables.

**Interfaces:**
- `ApplicationsPage` props: `{ bandBActions: ActionItem[]; executingId: string | null; lastExecuteResult: any; onExecute: (id: string) => void; nudgeResult: any; onGenerateNudge: () => void }`
- `ReferralsPage` props: `{ races: any[]; referrerInput: { shared_school: boolean; shared_past_company: boolean; same_department: boolean; seniority_match: boolean }; referrerScore: number | null; onReferrerInputChange: (next: typeof referrerInput) => void; onScoreReferrer: () => void }`
- `InterviewPrepPage` props: `{ interviewInput: { title: string; company: string; type: string }; interviewPrepResult: any; onInterviewInputChange: (next: typeof interviewInput) => void; onGeneratePrep: () => void }`
- `CalendarIntegrationsPage` props: `{ integrationsStatus: any; securityStatus: SecurityStatus | null; ghostJobs: any[] }`

- [ ] **Step 1: Create ApplicationsPage.tsx**

Source this from `App.tsx` lines 742-785 (the current "Phase 12" block) — same JSX, wrapped in a component taking props instead of reading `bandBActions`/`executingId`/etc. from the outer closure:

```tsx
import type { ActionItem } from '../types';

interface ApplicationsPageProps {
  bandBActions: ActionItem[];
  executingId: string | null;
  lastExecuteResult: any;
  onExecute: (id: string) => void;
  nudgeResult: any;
  onGenerateNudge: () => void;
}

export function ApplicationsPage({
  bandBActions,
  executingId,
  lastExecuteResult,
  onExecute,
  nudgeResult,
  onGenerateNudge,
}: ApplicationsPageProps) {
  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Applications</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '16px' }}>
        Real Playwright form-filling. It fills the real application and screenshots it for you —
        it never clicks Submit, even from here. Approving below runs the fill and shows the
        result; finishing the actual application is your own action, in your own browser.
      </p>
      {bandBActions.filter((a) => a.action_type === 'submit_application').length === 0 ? (
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Nothing queued for review.</span>
      ) : (
        <div className="scroll-x" style={{ display: 'grid', gap: '10px', marginBottom: '20px' }}>
          {bandBActions
            .filter((a) => a.action_type === 'submit_application')
            .map((act) => (
              <div
                key={act.action_id}
                style={{
                  padding: '14px',
                  background: 'rgba(255,255,255,0.03)',
                  borderRadius: '10px',
                  border: '1px solid var(--border-color)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  {String(act.payload?.job_url ?? '')}
                </div>
                <button
                  onClick={() => onExecute(act.action_id)}
                  disabled={executingId === act.action_id}
                  style={{ background: 'var(--accent-cyan)', color: '#fff', border: 'none', padding: '6px 14px', borderRadius: '6px', fontSize: '0.8rem', fontWeight: 600 }}
                >
                  {executingId === act.action_id ? 'Filling…' : 'Fill & preview'}
                </button>
              </div>
            ))}
        </div>
      )}
      {lastExecuteResult?.result?.screenshot_path && (
        <div style={{ padding: '12px', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', fontSize: '0.8rem', color: '#38bdf8', marginBottom: '20px' }}>
          Prepared: {lastExecuteResult.result.fields_filled} fields filled. Screenshot saved
          server-side at <code>{lastExecuteResult.result.screenshot_path}</code>.
        </div>
      )}
      <button onClick={onGenerateNudge} style={{ background: 'var(--accent-cyan)', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '6px', fontWeight: 600, fontSize: '0.85rem' }}>
        Generate Follow-Up Nudge
      </button>
      {nudgeResult && (
        <div style={{ marginTop: '12px', padding: '12px', background: 'rgba(0,0,0,0.3)', borderRadius: '8px', fontSize: '0.85rem', color: '#38bdf8' }}>
          Subject: {nudgeResult.subject}
          <br />
          <br />
          Body: {nudgeResult.body}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create ReferralsPage.tsx**

Source from `App.tsx` lines 578-633 (current "Phase 6" and "Phase 7" blocks, combined into one page):

```tsx
interface ReferrerInput {
  shared_school: boolean;
  shared_past_company: boolean;
  same_department: boolean;
  seniority_match: boolean;
}

interface ReferralsPageProps {
  races: any[];
  referrerInput: ReferrerInput;
  referrerScore: number | null;
  onReferrerInputChange: (next: ReferrerInput) => void;
  onScoreReferrer: () => void;
}

export function ReferralsPage({
  races,
  referrerInput,
  referrerScore,
  onReferrerInputChange,
  onScoreReferrer,
}: ReferralsPageProps) {
  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Referrals</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '24px' }}>
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
          <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Referrer 4-Factor Quality Scorer</h3>
          <div style={{ display: 'grid', gap: '8px', fontSize: '0.85rem' }}>
            <label>
              <input
                type="checkbox"
                checked={referrerInput.shared_school}
                onChange={(e) => onReferrerInputChange({ ...referrerInput, shared_school: e.target.checked })}
              />{' '}
              Shared School (+0.3)
            </label>
            <label>
              <input
                type="checkbox"
                checked={referrerInput.shared_past_company}
                onChange={(e) => onReferrerInputChange({ ...referrerInput, shared_past_company: e.target.checked })}
              />{' '}
              Shared Past Company (+0.4)
            </label>
            <label>
              <input
                type="checkbox"
                checked={referrerInput.same_department}
                onChange={(e) => onReferrerInputChange({ ...referrerInput, same_department: e.target.checked })}
              />{' '}
              Same Department (+0.2)
            </label>
            <label>
              <input
                type="checkbox"
                checked={referrerInput.seniority_match}
                onChange={(e) => onReferrerInputChange({ ...referrerInput, seniority_match: e.target.checked })}
              />{' '}
              Seniority Match (+0.1)
            </label>
            <button
              onClick={onScoreReferrer}
              style={{ marginTop: '8px', background: 'var(--accent-purple)', color: '#fff', border: 'none', padding: '8px', borderRadius: '6px', fontWeight: 600 }}
            >
              Calculate Referrer Score
            </button>
          </div>
        </div>

        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
          <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Calculated Warmth Score</h3>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--accent-purple)' }}>
            {referrerScore !== null ? `${(referrerScore * 100).toFixed(0)}%` : 'Click to score'}
          </div>
        </div>
      </div>

      <h3 style={{ fontSize: '1rem', marginBottom: '12px' }}>Warm-Path Races</h3>
      {races.length === 0 ? (
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          No warm-path races yet — starts automatically for Tier 1 matches when <code>jobos race</code>{' '}
          runs and a real LinkedIn connection exists at that company.
        </span>
      ) : (
        <div className="scroll-x" style={{ display: 'grid', gap: '10px' }}>
          {races.map((r, idx) => (
            <div key={idx} style={{ padding: '16px', background: 'rgba(168, 85, 247, 0.1)', borderRadius: '10px', border: '1px solid rgba(168, 85, 247, 0.3)' }}>
              <strong>
                {r.company} — {r.title}
              </strong>
              <div style={{ marginTop: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Status: {r.status}
                {r.resolution && ` (${r.resolution})`}
                {r.responded_channel && ` — response via ${r.responded_channel}`}
                {r.status === 'running' && ` — deadline ${new Date(r.deadline_at).toLocaleDateString()}`}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create InterviewPrepPage.tsx**

Source from `App.tsx` lines 714-740 (current "Phase 11" block) plus the "Phase 4" entailment-not-wired note (lines 506-521):

```tsx
interface InterviewInput {
  title: string;
  company: string;
  type: string;
}

interface InterviewPrepPageProps {
  interviewInput: InterviewInput;
  interviewPrepResult: any;
  onInterviewInputChange: (next: InterviewInput) => void;
  onGeneratePrep: () => void;
}

export function InterviewPrepPage({
  interviewInput,
  interviewPrepResult,
  onInterviewInputChange,
  onGeneratePrep,
}: InterviewPrepPageProps) {
  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Interview Prep</h2>

      <div style={{ padding: '12px 14px', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: '8px', color: '#fbbf24', fontSize: '0.85rem', marginBottom: '20px' }}>
        Not yet wired into the pipeline: <code>jobos/tailorer/entailment.py</code> implements a
        cross-family verification gate and is tested, but nothing calls it before tailored resume
        text ships.
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
          <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Target Role & Company</label>
          <input
            type="text"
            value={`${interviewInput.title} at ${interviewInput.company}`}
            onChange={(e) =>
              onInterviewInputChange({
                ...interviewInput,
                title: e.target.value.split(' at ')[0] || interviewInput.title,
              })
            }
            style={{ width: '100%', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border-color)', color: '#fff', padding: '8px', borderRadius: '6px', marginBottom: '12px' }}
          />
          <button
            onClick={onGeneratePrep}
            style={{ width: '100%', background: 'var(--accent-purple)', color: '#fff', border: 'none', padding: '8px', borderRadius: '6px', fontWeight: 600 }}
          >
            Generate Prep Pack
          </button>
        </div>

        <div style={{ background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px' }}>
          <h3 style={{ fontSize: '0.95rem', marginBottom: '12px' }}>Generated Prep Pack</h3>
          {interviewPrepResult ? (
            <pre style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', overflow: 'auto', maxHeight: '150px' }}>
              {JSON.stringify(interviewPrepResult, null, 2)}
            </pre>
          ) : (
            <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Click generate to preview prep pack...</span>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create CalendarIntegrationsPage.tsx**

Source from `App.tsx` lines 787-825 (current "Phase 13" and "Phase 14" blocks):

```tsx
import type { SecurityStatus } from '../types';

interface CalendarIntegrationsPageProps {
  integrationsStatus: any;
  securityStatus: SecurityStatus | null;
  ghostJobs: any[];
}

export function CalendarIntegrationsPage({
  integrationsStatus,
  securityStatus,
  ghostJobs,
}: CalendarIntegrationsPageProps) {
  return (
    <div>
      <h2 style={{ fontSize: '1.2rem', marginBottom: '16px' }}>Calendar & Integrations</h2>

      <div style={{ padding: '16px', background: 'rgba(99, 102, 241, 0.1)', borderRadius: '10px', border: '1px solid rgba(99, 102, 241, 0.3)', color: '#818cf8', fontSize: '0.9rem', marginBottom: '10px' }}>
        Gmail: <strong>{integrationsStatus ? integrationsStatus.gmail : 'Checking…'}</strong>
        <br />
        Calendar: <strong>{integrationsStatus ? integrationsStatus.calendar : 'Checking…'}</strong>
      </div>
      <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '24px' }}>
        "Configured" means a Composio key is set — it does not mean a human has completed the
        OAuth connection for this tenant. That can only be verified with a live Composio call.
      </p>

      <details>
        <summary style={{ cursor: 'pointer', fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '12px' }}>
          Advanced: security & circuit breaker
        </summary>
        <div style={{ display: 'grid', gap: '12px', marginTop: '12px' }}>
          <div style={{ padding: '12px', background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', borderRadius: '8px', color: '#f87171', fontSize: '0.85rem' }}>
            {securityStatus ? (
              <>
                Circuit Breaker: {securityStatus.circuit_breaker.action_counts.applies}/
                {securityStatus.circuit_breaker.limits.applies} daily applies,{' '}
                {securityStatus.circuit_breaker.action_counts.emails}/
                {securityStatus.circuit_breaker.limits.emails} daily emails used
              </>
            ) : (
              'Loading circuit breaker status…'
            )}
          </div>
          <div style={{ padding: '12px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', fontSize: '0.85rem' }}>
            Ghost Job Detector: {ghostJobs.length} stale listings flagged (&gt;60 days inactive)
            <span style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              Checks one fixture job, not this tenant's real listings.
            </span>
          </div>
          {securityStatus && (
            <div style={{ display: 'grid', gap: '8px' }}>
              {securityStatus.prohibitions.map((p, idx) => (
                <div key={idx} style={{ padding: '10px 14px', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: '8px', color: '#34d399', fontSize: '0.85rem' }}>
                  ✓ {p}
                </div>
              ))}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
```

- [ ] **Step 5: Verify it compiles**

Run: `cd dashboard && npx tsc --noEmit`

- [ ] **Step 6: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add dashboard/src/pages/ApplicationsPage.tsx dashboard/src/pages/ReferralsPage.tsx dashboard/src/pages/InterviewPrepPage.tsx dashboard/src/pages/CalendarIntegrationsPage.tsx
git commit -m "refactor(dashboard): relocate Applications/Referrals/Interview Prep/Calendar into page components

Mechanical extraction from the old phase-numbered App.tsx blocks —
same JSX, same behavior, now taking props instead of reading the
parent's closure. The old security/RLS panel moves under an
'Advanced' details toggle on the Calendar & Integrations page."
```

---

### Task 10: Wire it all together in App.tsx

**Files:**
- Modify: `dashboard/src/App.tsx` (full rewrite of the return statement and state wiring; keep the login-gate block and most `useState`/handler logic)

**Interfaces:**
- Consumes: everything produced by Tasks 4-9.

- [ ] **Step 1: Rewrite App.tsx**

Replace the whole file with:

```tsx
import { useState, useEffect } from 'react';
import { Cpu } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { ProfilePage } from './pages/ProfilePage';
import { JobMatchesPage } from './pages/JobMatchesPage';
import { ApplicationsPage } from './pages/ApplicationsPage';
import { ReferralsPage } from './pages/ReferralsPage';
import { InterviewPrepPage } from './pages/InterviewPrepPage';
import { CalendarIntegrationsPage } from './pages/CalendarIntegrationsPage';
import { ReviewInboxPage } from './pages/ReviewInboxPage';
import type { PipelineStats, SecurityStatus, ActionItem } from './types';

export function App() {
  const [activeSection, setActiveSection] = useState<string>('matches');
  const [apiToken, setApiToken] = useState<string>(() => localStorage.getItem('jobos_token') || '');
  const [tokenInput, setTokenInput] = useState<string>('');
  const [authError, setAuthError] = useState<string>('');

  const [stats, setStats] = useState<PipelineStats | null>(null);
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const [bandBActions, setBandBActions] = useState<ActionItem[]>([]);
  const [pendingActions, setPendingActions] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  const [referrerInput, setReferrerInput] = useState({ shared_school: true, shared_past_company: true, same_department: true, seniority_match: true });
  const [referrerScore, setReferrerScore] = useState<number | null>(null);

  const [interviewInput, setInterviewInput] = useState({ title: 'Tech Lead', company: 'Stripe', type: 'technical' });
  const [interviewPrepResult, setInterviewPrepResult] = useState<any>(null);

  const [nudgeResult, setNudgeResult] = useState<any>(null);
  const [integrationsStatus, setIntegrationsStatus] = useState<any>(null);
  const [ghostJobs, setGhostJobs] = useState<any[]>([]);
  const [careerGraph, setCareerGraph] = useState<any>(null);
  const [races, setRaces] = useState<any[]>([]);
  const [shadowModeReal, setShadowModeReal] = useState<boolean | null>(null);
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [lastExecuteResult, setLastExecuteResult] = useState<any>(null);

  const fetchAllPhaseData = async () => {
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${apiToken}` };
      const [sRes, secRes, jRes, bRes, pendRes, intRes, ghostRes, cgRes, raceRes, smRes] = await Promise.all([
        fetch('/api/stats', { headers }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('/api/security/status', { headers }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('/api/jobs', { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/actions?band=B', { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/actions?status=pending', { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/integrations/status').then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('/api/calibration/ghost-jobs').then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/career-graph/summary', { headers }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('/api/warmpath/races', { headers }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
        fetch('/api/shadow-mode', { headers }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ]);

      setStats(sRes);
      setSecurityStatus(secRes);
      setJobs(jRes);
      setBandBActions(bRes);
      setPendingActions(pendRes);
      setIntegrationsStatus(intRes);
      setGhostJobs(ghostRes);
      setCareerGraph(cgRes);
      setRaces(raceRes);
      setShadowModeReal(smRes?.enabled ?? null);
    } catch (err) {
      console.error('API error fetching dashboard data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (apiToken) fetchAllPhaseData();
  }, [apiToken]);

  const handleSignIn = async () => {
    const candidate = tokenInput.trim();
    if (!candidate) return;
    const res = await fetch('/api/stats', { headers: { Authorization: `Bearer ${candidate}` } });
    if (!res.ok) {
      setAuthError(res.status === 401 ? 'Token rejected. Check it and try again.' : `Server error (${res.status}).`);
      return;
    }
    localStorage.setItem('jobos_token', candidate);
    setAuthError('');
    setApiToken(candidate);
  };

  const handleScoreReferrer = async () => {
    const res = await fetch('/api/referral/score', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(referrerInput),
    }).then((r) => r.json());
    setReferrerScore(res.score);
  };

  const handleGeneratePrep = async () => {
    const res = await fetch('/api/interview/prep', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: interviewInput.title, company: interviewInput.company, interview_type: interviewInput.type }),
    }).then((r) => r.json());
    setInterviewPrepResult(res);
  };

  const handleStatusNudge = async () => {
    const res = await fetch('/api/followup/nudge?company=Stripe&role=Staff+AI+Engineer&days_since=5').then((r) => r.json());
    setNudgeResult(res);
  };

  const handleExecuteAction = async (id: string) => {
    setExecutingId(id);
    try {
      const res = await fetch(`/api/actions/${id}/execute`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${apiToken}` },
      });
      const body = await res.json();
      setLastExecuteResult(body);
      setBandBActions(bandBActions.filter((a) => a.action_id !== id));
      setPendingActions(pendingActions.filter((a) => a.action_id !== id));
    } finally {
      setExecutingId(null);
    }
  };

  const handleInboxActed = (actionId: string) => {
    setPendingActions(pendingActions.filter((a) => a.action_id !== actionId));
    setBandBActions(bandBActions.filter((a) => a.action_id !== actionId));
  };

  const handleToggleShadowMode = async () => {
    const next = !shadowModeReal;
    const res = await fetch(`/api/shadow-mode?enabled=${next}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiToken}` },
    }).then((r) => r.json());
    setShadowModeReal(res.enabled);
  };

  if (!apiToken) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
        <div style={{ padding: '32px', maxWidth: '520px', width: '100%', border: '1px solid var(--border-color)', borderRadius: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <div style={{ background: 'linear-gradient(135deg, #6366f1, #06b6d4)', padding: '10px', borderRadius: '12px', display: 'flex' }}>
              <Cpu size={24} color="#fff" />
            </div>
            <h1 style={{ fontSize: '1.4rem' }}>JOBOS</h1>
          </div>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '20px' }}>
            Paste your API token to continue. Mint one with:
          </p>
          <code style={{ display: 'block', background: 'rgba(0,0,0,0.35)', padding: '10px 12px', borderRadius: '8px', fontSize: '0.75rem', color: '#06b6d4', marginBottom: '20px', overflowX: 'auto' }}>
            jobos --user-id &lt;your-uuid&gt; token create --name browser
          </code>
          <input
            type="password"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSignIn(); }}
            placeholder="jobos_..."
            style={{ width: '100%', padding: '12px', borderRadius: '8px', border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.05)', color: '#fff', fontSize: '0.9rem', marginBottom: '12px' }}
          />
          {authError && <p style={{ color: '#f87171', fontSize: '0.8rem', marginBottom: '12px' }}>{authError}</p>}
          <button
            onClick={handleSignIn}
            style={{ width: '100%', padding: '12px', borderRadius: '8px', border: 'none', background: 'linear-gradient(135deg, #6366f1, #06b6d4)', color: '#fff', fontSize: '0.9rem', cursor: 'pointer', fontWeight: 600 }}
          >
            Sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar activeSection={activeSection} onSelect={setActiveSection} />
      <div className="app-content">
        <TopBar
          onSync={fetchAllPhaseData}
          syncing={loading}
          shadowModeReal={shadowModeReal}
          onToggleShadowMode={handleToggleShadowMode}
          onSignOut={() => { localStorage.removeItem('jobos_token'); setApiToken(''); }}
          pendingCount={pendingActions.length}
          onOpenInbox={() => setActiveSection('inbox')}
        />

        {activeSection === 'inbox' && (
          <ReviewInboxPage token={apiToken} pending={pendingActions} onActed={handleInboxActed} />
        )}
        {activeSection === 'profile' && (
          <ProfilePage token={apiToken} careerGraph={careerGraph} onImported={fetchAllPhaseData} />
        )}
        {activeSection === 'matches' && <JobMatchesPage token={apiToken} jobs={jobs} />}
        {activeSection === 'applications' && (
          <ApplicationsPage
            bandBActions={bandBActions}
            executingId={executingId}
            lastExecuteResult={lastExecuteResult}
            onExecute={handleExecuteAction}
            nudgeResult={nudgeResult}
            onGenerateNudge={handleStatusNudge}
          />
        )}
        {activeSection === 'referrals' && (
          <ReferralsPage
            races={races}
            referrerInput={referrerInput}
            referrerScore={referrerScore}
            onReferrerInputChange={setReferrerInput}
            onScoreReferrer={handleScoreReferrer}
          />
        )}
        {activeSection === 'interview-prep' && (
          <InterviewPrepPage
            interviewInput={interviewInput}
            interviewPrepResult={interviewPrepResult}
            onInterviewInputChange={setInterviewInput}
            onGeneratePrep={handleGeneratePrep}
          />
        )}
        {activeSection === 'calendar' && (
          <CalendarIntegrationsPage
            integrationsStatus={integrationsStatus}
            securityStatus={securityStatus}
            ghostJobs={ghostJobs}
          />
        )}
      </div>
    </div>
  );
}

export default App;
```

Note: `stats` is fetched but no longer rendered anywhere in this version (the old top-metrics strip is dropped — the sidebar + inbox badge carry that job now). If a metrics strip is wanted back, it's a follow-up, not part of this MVP scope. Also note the login screen intentionally drops the `glass-panel` class per the design direction — verify visually in Step 2 that it still reads clearly against the flat body background.

- [ ] **Step 2: Compile check**

Run: `cd dashboard && npx tsc --noEmit`
Expected: no errors. Fix any prop-type mismatches against Tasks 6-9's interfaces before continuing.

- [ ] **Step 3: Manual browser verification**

1. Start the dev server preview (`mcp__Claude_Browser__preview_start` with the dashboard's launch config, or whatever this session already has running).
2. Reload, sign in with the existing token.
3. Screenshot the default view (Job Matches) — confirm sidebar shows 6 items, no numbered "Phase" labels anywhere.
4. Click each sidebar item, screenshot each, confirm real data renders (or honest empty state) and no console errors (`mcp__Claude_Browser__read_console_messages`).
5. Click "Needs your review" — confirm it shows the `pendingActions` count and list.
6. Resize to 850px width (`mcp__Claude_Browser__resize_window`), confirm sidebar collapses to icon rail and no horizontal page scroll.

- [ ] **Step 4: Commit**

```bash
cd "/Users/nani/Downloads/primeneuro/jobos"
git add dashboard/src/App.tsx
git commit -m "refactor(dashboard): wire sidebar + pages into App.tsx, drop the 15-phase grid

App.tsx keeps the login gate and the shared state/fetch/handler
logic; the phase-numbered grid and 845-line mega-return are gone,
replaced by Sidebar + TopBar + one page component per workflow
section. Matches docs/superpowers/specs/2026-08-12-workflow-dashboard-design.md."
```

---

## Self-Review Notes

- **Spec coverage:** all 6 sidebar sections (Tasks 6-9), review inbox (Task 6), 3 new endpoint groups = 4 routes (Tasks 1-3), design-direction CSS (Task 5), LinkedIn upload (Tasks 2, 8), resume generation (Tasks 3, 7) — every spec section has a task.
- **Dropped from spec, called out explicitly:** the top metrics strip (Jobs Tracked / Applications Sent / etc.) wasn't in the spec's component list and has no home in the new IA; Task 10 drops it rather than inventing a placement. Flag this to the user after execution in case they want it back somewhere.
- **Type consistency checked:** `ActionItem` (Task 4) matches the shape returned by both `dequeue_batch` and the new `list_pending` (Task 1) — `action_id`, `action_type`, `band`, `status`, `payload`. `SecurityStatus` (Task 4) matches what `CalendarIntegrationsPage` (Task 9) reads. `Job` (Task 4) is loose (`[key: string]: unknown`) because `/api/jobs` isn't part of this plan's scope and its exact shape wasn't pinned down — `JobMatchesPage` only relies on `title`, `company`, `location`, `tier`, `ev_score`, `id`; if `/api/jobs` doesn't return an `id` field per job, Task 7's `generateResume(job)` call needs `job.id` fixed to whatever the real field name is — check this first thing in Task 7 by hitting `/api/jobs` directly.
