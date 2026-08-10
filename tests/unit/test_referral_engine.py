"""Unit tests for the referral finder, network mapper and sequence generator."""

import pytest

from jobos.referral.finder import find_referrers
from jobos.referral.network_mapper import map_existing_network
from jobos.referral.sequence import (
    _parse_touches,
    generate_referral_sequence,
    has_real_personalization,
)

USER_PROFILE = {
    "name": "Asha",
    "schools": ["IIT Madras"],
    "past_companies": ["Freshworks"],
}


class FakeApollo:
    def __init__(self, people):
        self.people = people
        self.calls = []

    async def search_people(self, company_domain, titles=None, per_page=10):
        self.calls.append(company_domain)
        return self.people


class FakeIcypeas:
    def __init__(self, email):
        self.email = email
        self.calls = []

    async def find_email(self, first_name, last_name, domain):
        self.calls.append((first_name, last_name, domain))
        return self.email


async def test_finder_returns_nothing_when_provider_has_no_people():
    """No candidates must mean an empty list — never a fabricated contact."""
    result = await find_referrers("acme.com", USER_PROFILE, apollo=FakeApollo([]))
    assert result == []


async def test_finder_never_invents_an_email():
    apollo = FakeApollo([{"first_name": "Ravi", "last_name": "K", "title": "SWE"}])

    result = await find_referrers("acme.com", USER_PROFILE, apollo=apollo)

    assert len(result) == 1
    assert result[0]["email"] is None
    assert result[0]["email_verified"] is False
    # The previous implementation guessed referral@<domain>.
    assert "referral@acme.com" not in str(result)


async def test_finder_detects_real_shared_history():
    apollo = FakeApollo(
        [
            {
                "first_name": "Ravi",
                "last_name": "Kumar",
                "title": "Engineering Manager",
                "email": "ravi@acme.com",
                "employment_history": [
                    {"organization_name": "IIT Madras", "kind": "education"},
                    {"organization_name": "Freshworks", "current": False},
                    {"organization_name": "Acme", "current": True},
                ],
            }
        ]
    )

    [candidate] = await find_referrers("acme.com", USER_PROFILE, apollo=apollo)

    assert candidate["shared_school"] == ["iit madras"]
    assert candidate["shared_past_company"] == ["freshworks"]
    # Current employer is not shared history.
    assert "acme" not in candidate["shared_past_company"]
    assert candidate["warmth_score"] == 1.0


async def test_finder_ranks_warmer_candidates_first():
    apollo = FakeApollo(
        [
            {"first_name": "Cold", "last_name": "Lead", "title": "SWE"},
            {
                "first_name": "Warm",
                "last_name": "Lead",
                "title": "SWE",
                "email": "warm@acme.com",
                "employment_history": [{"organization_name": "Freshworks", "current": False}],
            },
        ]
    )

    results = await find_referrers("acme.com", USER_PROFILE, apollo=apollo)

    assert results[0]["name"] == "Warm Lead"


async def test_finder_falls_back_to_icypeas_when_email_locked():
    apollo = FakeApollo(
        [{"first_name": "Ravi", "last_name": "Kumar", "email": "email_not_unlocked@domain.com"}]
    )
    icypeas = FakeIcypeas("ravi.kumar@acme.com")

    [candidate] = await find_referrers("acme.com", USER_PROFILE, apollo=apollo, icypeas=icypeas)

    assert candidate["email"] == "ravi.kumar@acme.com"
    assert icypeas.calls == [("Ravi", "Kumar", "acme.com")]


async def test_network_mapper_matches_across_name_and_domain_forms():
    contacts = [
        {"name": "A", "company": "Acme Technologies Pvt Ltd"},
        {"name": "B", "company": "acme.com"},
        {"name": "C", "company": "Unrelated Corp"},
    ]

    leads = await map_existing_network(contacts, ["Acme"])

    assert sorted(lead["name"] for lead in leads) == ["A", "B"]


async def test_network_mapper_ignores_contacts_without_a_company():
    leads = await map_existing_network([{"name": "A"}], ["Acme"])
    assert leads == []


def test_personalization_gate_requires_real_common_ground():
    assert has_real_personalization({"shared_school": ["iit madras"]}) is True
    assert has_real_personalization({"shared_past_company": ["freshworks"]}) is True
    assert has_real_personalization({"shared_school": [], "shared_past_company": []}) is False
    assert has_real_personalization({}) is False


async def test_sequence_dropped_when_no_shared_context():
    """The gate must drop cold leads rather than emailing them."""
    result = await generate_referral_sequence(
        referrer={"name": "Ravi", "shared_school": [], "shared_past_company": []},
        job={"title": "Backend Engineer", "company": "Acme"},
        user_profile=USER_PROFILE,
    )
    assert result == []


async def test_sequence_uses_llm_and_returns_three_touches(mocker):
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

    touches = await generate_referral_sequence(
        referrer={"name": "Ravi", "shared_past_company": ["freshworks"]},
        job={"title": "Backend Engineer", "company": "Acme"},
        user_profile=USER_PROFILE,
    )

    assert [t["send_delay_hours"] for t in touches] == [0, 72, 144]
    assert touches[0]["subject"] == "s1"


async def test_sequence_returns_empty_when_model_fails(mocker):
    """A provider outage must not produce a half-written email."""
    mocker.patch(
        "jobos.referral.sequence.acompletion",
        side_effect=RuntimeError("provider down"),
    )

    result = await generate_referral_sequence(
        referrer={"name": "Ravi", "shared_past_company": ["freshworks"]},
        job={"title": "Backend Engineer", "company": "Acme"},
        user_profile=USER_PROFILE,
    )
    assert result == []


@pytest.mark.parametrize(
    "raw",
    [
        "not json at all",
        '[{"subject":"only","body":"one"}]',
        '[{"subject":"","body":"b"},{"subject":"s","body":"b"},{"subject":"s","body":"b"}]',
    ],
)
def test_parse_touches_rejects_malformed_output(raw):
    assert _parse_touches(raw) is None


def test_parse_touches_tolerates_code_fences():
    fenced = '```json\n[{"subject":"s1","body":"b1"},{"subject":"s2","body":"b2"},{"subject":"s3","body":"b3"}]\n```'
    touches = _parse_touches(fenced)
    assert touches is not None
    assert len(touches) == 3
