"""Integration tests for GET /api/integrations/status and GET /api/calibration/ghost-jobs.

Neither route sits behind authenticated_tenant, so there's no 401 case here.
"""

import httpx
import pytest

from jobos.api import main as api_main
from jobos.calibration.ghost_tracker import detect_ghost_jobs
from jobos.config import settings

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _client(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_integrations_status_reflects_no_key_configured_honestly(db_pool):
    """The endpoint's own docstring: 'configured' means only that a Composio
    API key is set, never that OAuth has actually been completed. In this
    test environment no key is configured, so the honest answer is
    not_configured for all three — never a fabricated 'CONNECTED'."""
    assert settings.composio.api_key == "", "sanity check: test env must have no Composio key"

    async with await _client(db_pool) as client:
        response = await client.get("/api/integrations/status")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "composio": "not_configured",
        "gmail": "not_configured",
        "calendar": "not_configured",
    }


async def test_ghost_jobs_matches_detect_ghost_jobs_directly(db_pool):
    """The endpoint hardcodes one fixed test job rather than reading real
    listings (see main.py) — assert its output against calling
    detect_ghost_jobs with that same fixed input, not a hand-picked number."""
    fixed_input = [{"job_id": "ghost-1", "days_active": 75, "title": "Stale Engineer Role"}]
    expected = await detect_ghost_jobs(fixed_input)
    assert expected, "sanity check: 75 days active must exceed the staleness threshold"

    async with await _client(db_pool) as client:
        response = await client.get("/api/calibration/ghost-jobs")

    assert response.status_code == 200
    assert response.json() == expected
