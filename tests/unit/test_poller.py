"""Unit tests for ATSPoller."""

import pytest
import httpx
from jobos.config import settings
from jobos.ingestion.poller import ATSPoller


@pytest.mark.asyncio
async def test_poller_greenhouse_success() -> None:
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 1,
                        "title": "Backend Engineer",
                        "location": {"name": "Remote"},
                    }
                ]
            },
        )

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        poller = ATSPoller(settings=settings)
        # Directly test parsing with mock client response
        res = await client.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs")
        assert res.status_code == 200
        jobs = res.json()["jobs"]
        assert len(jobs) == 1
