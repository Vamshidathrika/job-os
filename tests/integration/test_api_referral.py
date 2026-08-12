"""Integration tests for POST /api/referral/score and GET /api/referral/candidates.

Neither route sits behind authenticated_tenant (no Depends() on either in
jobos/api/main.py), so there is no 401 case in this file.

/api/referral/candidates calls find_referrers(..., apollo=None) with no way
for a caller to inject a provider — per find_referrers' own contract, no
provider configured means "no data to search", not a fabricated candidate,
so the only honest assertion here is that it returns []. Seeding rows into
`people` would not affect this endpoint's response at all, since it never
queries the database.
"""

import httpx
import pytest

from jobos.api import main as api_main
from jobos.referral.finder import find_referrers
from jobos.referral.scorer import score_referrer

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _client(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.parametrize(
    "payload",
    [
        {"shared_school": True, "shared_past_company": True, "same_department": True, "seniority_match": True},
        {"shared_school": True, "shared_past_company": False, "same_department": False, "seniority_match": False},
        {"shared_school": False, "shared_past_company": False, "same_department": False, "seniority_match": False},
    ],
)
async def test_score_matches_score_referrer_directly(db_pool, payload):
    expected = score_referrer(
        {
            "shared_school": payload["shared_school"],
            "shared_past_company": payload["shared_past_company"],
            "same_department": payload["same_department"],
            "seniority_match": payload["seniority_match"],
        },
        {},
    )

    async with await _client(db_pool) as client:
        response = await client.post("/api/referral/score", json=payload)

    assert response.status_code == 200
    assert response.json() == {"score": expected}


async def test_candidates_with_no_provider_configured_returns_empty_not_fabricated(db_pool):
    expected = await find_referrers(
        "postman.com", {"schools": ["Stanford"], "past_companies": ["Google"]}, apollo=None
    )
    assert expected == []

    async with await _client(db_pool) as client:
        response = await client.get("/api/referral/candidates")

    assert response.status_code == 200
    assert response.json() == []
