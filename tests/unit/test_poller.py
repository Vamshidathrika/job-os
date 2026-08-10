"""Unit tests for ATSPoller."""

import httpx
import pytest

from jobos.config import settings
from jobos.ingestion.poller import ATSPoller

GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 1,
            "title": "Backend Engineer",
            "location": {"name": "Remote"},
            "content": "Build services.",
        }
    ]
}


def _poller_with(handler) -> ATSPoller:
    """An ATSPoller whose HTTP calls are served by `handler`."""
    poller = ATSPoller(settings=settings)
    poller.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return poller


@pytest.mark.asyncio
async def test_poller_greenhouse_success() -> None:
    poller = _poller_with(lambda request: httpx.Response(200, json=GREENHOUSE_PAYLOAD))

    jobs = await poller.poll_company(
        company_domain="acme.com", ats_type="greenhouse", ats_identifier="acme"
    )

    assert len(jobs) == 1
    assert jobs[0]["external_id"] == "1"
    assert jobs[0]["title"] == "Backend Engineer"
    assert jobs[0]["location"] == "Remote"


@pytest.mark.asyncio
async def test_poller_hits_the_greenhouse_board_url() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=GREENHOUSE_PAYLOAD)

    poller = _poller_with(handler)
    await poller.poll_company(
        company_domain="acme.com", ats_type="greenhouse", ats_identifier="acme-board"
    )

    assert "boards-api.greenhouse.io/v1/boards/acme-board/jobs" in seen[0]


@pytest.mark.asyncio
async def test_unknown_ats_returns_no_jobs_without_calling_out() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    poller = _poller_with(handler)
    jobs = await poller.poll_company(
        company_domain="acme.com", ats_type="carrier-pigeon", ats_identifier="acme"
    )

    assert jobs == []
    assert called is False


@pytest.mark.asyncio
async def test_provider_failure_degrades_to_empty_not_an_exception() -> None:
    """One unreachable board must not abort the whole ingestion cycle."""
    poller = _poller_with(lambda request: httpx.Response(500))

    jobs = await poller.poll_company(
        company_domain="acme.com", ats_type="greenhouse", ats_identifier="acme"
    )

    assert jobs == []
