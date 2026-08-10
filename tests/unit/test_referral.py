"""Unit tests for Referral Engine."""

from __future__ import annotations

import pytest
from jobos.referral.scorer import score_referrer
from jobos.referral.sequence import generate_referral_sequence
from jobos.referral.network_mapper import map_existing_network


def test_score_referrer_shared_school() -> None:
    """Shared school adds +0.3 to referrer score."""
    referrer = {"shared_school": True, "shared_past_company": False}
    user_profile: dict[str, object] = {}
    score = score_referrer(referrer, user_profile)
    assert score == pytest.approx(0.3)


def test_score_referrer_shared_company() -> None:
    """Shared past company adds +0.4 to referrer score."""
    referrer = {"shared_school": False, "shared_past_company": True}
    user_profile: dict[str, object] = {}
    score = score_referrer(referrer, user_profile)
    assert score == pytest.approx(0.4)


def test_score_referrer_all_signals() -> None:
    """All signals active caps at 1.0."""
    referrer = {
        "shared_school": True,
        "shared_past_company": True,
        "same_department": True,
        "seniority_match": True,
    }
    user_profile: dict[str, object] = {}
    score = score_referrer(referrer, user_profile)
    assert score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_generate_referral_sequence(mocker) -> None:
    """3-touch sequence generation returns 3 emails."""
    mocker.patch(
        "jobos.referral.sequence.acompletion",
        return_value={
            "choices": [
                {
                    "message": {
                        "content": (
                            '[{"subject":"s1","body":"b1"},'
                            '{"subject":"s2","body":"b2"},'
                            '{"subject":"s3","body":"b3"}]'
                        )
                    }
                }
            ]
        },
    )
    # A sequence is only generated when there is real common ground to cite.
    referrer = {
        "name": "John",
        "email": "john@company.com",
        "shared_past_company": ["freshworks"],
    }
    job = {"title": "Senior Engineer", "company": "Acme"}
    user_profile = {"name": "Jane"}
    sequence = await generate_referral_sequence(referrer, job, user_profile)
    assert len(sequence) == 3
    # Each email should have subject and body
    for email in sequence:
        assert "subject" in email
        assert "body" in email


@pytest.mark.asyncio
async def test_referral_sequence_gated_without_shared_context() -> None:
    """No common ground means no email — that is the personalization gate."""
    sequence = await generate_referral_sequence(
        {"name": "John", "email": "john@company.com"},
        {"title": "Senior Engineer", "company": "Acme"},
        {"name": "Jane"},
    )
    assert sequence == []


@pytest.mark.asyncio
async def test_map_existing_network() -> None:
    """Existing contacts mapped to target companies."""
    contacts = [
        {"email": "contact@target.com", "name": "Jane", "company": "Target Corp"},
    ]
    companies = ["Target Corp"]
    mapping = await map_existing_network(contacts, companies)
    assert isinstance(mapping, list)
