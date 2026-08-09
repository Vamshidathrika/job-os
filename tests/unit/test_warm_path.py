"""Unit tests for Warm-Path 7-Day Race Engine."""

import pytest
from jobos.warm_path.decision import should_hold_application, select_fallback_band
from jobos.warm_path.race import WarmPathRace


def test_should_hold_application_tier1() -> None:
    """Tier 1 job with high scores should be held for warm path."""
    assert should_hold_application(match_score=0.9, ev_score=0.8, tier=1) is True


def test_should_not_hold_tier3() -> None:
    """Tier 3 job should not be held."""
    assert should_hold_application(match_score=0.9, ev_score=0.8, tier=3) is False


def test_select_fallback_band_7_days_no_responses() -> None:
    """After 7 days with no warm responses, fallback to Band A (auto-apply)."""
    assert select_fallback_band(days_elapsed=7, warm_responses=0) == "A"


def test_select_fallback_band_with_responses() -> None:
    """Any warm responses should escalate to Band C (human only)."""
    assert select_fallback_band(days_elapsed=3, warm_responses=1) == "C"


def test_select_fallback_band_mid_race() -> None:
    """Mid-race with no responses should be Band B (queue for review)."""
    assert select_fallback_band(days_elapsed=3, warm_responses=0) == "B"


@pytest.mark.asyncio
async def test_warm_path_race_resolve() -> None:
    """Test race resolution returns valid outcome structure."""
    race = WarmPathRace(job_id="j-123", tenant_id="t-456", channels=["REFERRAL", "RECRUITER"])
    result = await race.resolve_race()
    assert "outcome" in result
    assert "channel" in result
    assert "days_elapsed" in result
    assert result["outcome"] in ("referral_reply", "recruiter_reply", "cold_apply_fallback")
