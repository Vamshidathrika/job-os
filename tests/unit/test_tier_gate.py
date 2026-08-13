"""Unit tests for classify_tier's warm-connection tiering behavior."""

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


def test_warm_contact_below_its_own_lower_bar_still_falls_through():
    # has_warm_contact=True does not blanket-promote to Tier 1 — the lower
    # bar (0.50/0.40) still has to be cleared.
    assert classify_tier(match_score=0.45, ev_score=0.45, has_warm_contact=True) == 3


def test_standard_bar_still_reaches_tier_1_without_a_warm_contact():
    assert classify_tier(match_score=0.70, ev_score=0.65, has_warm_contact=False) == 1
