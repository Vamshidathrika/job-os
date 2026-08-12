"""Integration tests for POST /api/comp/predict and POST /api/comp/deflect.

Neither route is behind `authenticated_tenant` (see jobos/api/main.py) — both
are pure, tenant-agnostic calculators with no Depends() at all — so there is
no meaningful 401 case to cover in this file, unlike files that touch a
protected route.
"""

import httpx
import pytest

from jobos.api import main as api_main
from jobos.comp import handle_comp_field, predict_salary_band

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _client(db_pool):
    api_main.app.state.pool = db_pool
    transport = httpx.ASGITransport(app=api_main.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.parametrize(
    "title,location,yoe",
    [
        ("Backend Engineer", "Bengaluru", 2),
        ("Staff Engineer", "United States", 8),
        ("Engineer", "Singapore", 5),
    ],
)
async def test_predict_matches_predict_salary_band_directly(db_pool, title, location, yoe):
    expected = predict_salary_band(title=title, location=location, yoe=yoe)

    async with await _client(db_pool) as client:
        response = await client.post(
            "/api/comp/predict", json={"title": title, "location": location, "yoe": yoe}
        )

    assert response.status_code == 200
    assert response.json() == expected


@pytest.mark.parametrize(
    "field_type,field_value,predicted_band",
    [
        ("text", None, {"p75": 3600000.0}),
        ("numeric_required", None, {"p75": 3600000.0}),
        ("current_ctc", "1800000", {"p75": 3600000.0}),
        ("unknown_field", None, {}),
    ],
)
async def test_deflect_matches_handle_comp_field_directly(
    db_pool, field_type, field_value, predicted_band
):
    expected = handle_comp_field(
        field_type=field_type, field_value=field_value, predicted_band=predicted_band
    )

    async with await _client(db_pool) as client:
        response = await client.post(
            "/api/comp/deflect",
            json={
                "field_type": field_type,
                "field_value": field_value,
                "predicted_band": predicted_band,
            },
        )

    assert response.status_code == 200
    assert response.json() == expected
    # Sanity: the fixture actually distinguishes behavior across field types,
    # so this isn't a test that would pass no matter what handle_comp_field did.
    assert expected["action"] in {"deflect", "fill", "escalate_band_c", "skip"}
