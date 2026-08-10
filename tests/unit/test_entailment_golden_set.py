"""Entailment gate behaviour tests.

The previous version of this file was circular: its "hallucinated" claims were
character-for-character the strings hardcoded in the implementation's keyword
list, so a 95% "accuracy benchmark" was guaranteed regardless of whether any
verification happened. These tests drive the verifier's decision path instead —
what the gate does with a verdict, and what it does when it cannot get one.
"""

import json

import pytest

from jobos.tailorer import verify_entailment

EVIDENCE = [
    {"id": "b1", "bullet_text": "Built a Redis caching layer, cutting P99 latency 45%", "company": "Acme"},
    {"id": "b2", "bullet_text": "Managed a team of 4 engineers", "company": "Acme"},
]

# Distinct families: openrouter='mixed' vs nim='llama'.
TAILOR = "openrouter"
VERIFIER = "nim"


def _verdict(entailed: bool, unsupported: list[str] | None = None) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"entailed": entailed, "unsupported_claims": unsupported or []}
                    )
                }
            }
        ]
    }


async def test_supported_claim_passes(mocker):
    mocker.patch("jobos.tailorer.entailment.acompletion", return_value=_verdict(True))

    assert await verify_entailment(
        "Built a Redis caching layer that cut P99 latency 45%", EVIDENCE, TAILOR, VERIFIER
    ) is True


async def test_unsupported_claim_is_rejected(mocker):
    """A fabrication the old keyword list never knew about must still fail."""
    mocker.patch(
        "jobos.tailorer.entailment.acompletion",
        return_value=_verdict(False, ["Led a team of 500 engineers at Google"]),
    )

    assert await verify_entailment(
        "Led a team of 500 engineers at Google", EVIDENCE, TAILOR, VERIFIER
    ) is False


async def test_contradictory_verdict_fails_closed(mocker):
    """entailed=true while naming unsupported claims is self-contradictory."""
    mocker.patch(
        "jobos.tailorer.entailment.acompletion",
        return_value=_verdict(True, ["Awarded the Turing Award"]),
    )

    assert await verify_entailment("Awarded the Turing Award", EVIDENCE, TAILOR, VERIFIER) is False


async def test_verifier_outage_fails_closed(mocker):
    """No verdict must never mean 'approved' — this text goes to employers."""
    mocker.patch(
        "jobos.tailorer.entailment.acompletion", side_effect=RuntimeError("provider down")
    )

    assert await verify_entailment("Built a caching layer", EVIDENCE, TAILOR, VERIFIER) is False


@pytest.mark.parametrize(
    "reply",
    [
        "looks fine to me",
        '{"unsupported_claims": []}',       # missing the verdict field
        '{"entailed": "yes"}',              # wrong type
        "",
    ],
)
async def test_unparseable_verdict_fails_closed(mocker, reply):
    mocker.patch(
        "jobos.tailorer.entailment.acompletion",
        return_value={"choices": [{"message": {"content": reply}}]},
    )

    assert await verify_entailment("Built a caching layer", EVIDENCE, TAILOR, VERIFIER) is False


async def test_no_evidence_cannot_entail_anything(mocker):
    """With nothing retrieved, nothing is verifiable — refuse rather than pass."""
    llm = mocker.patch("jobos.tailorer.entailment.acompletion")

    assert await verify_entailment("Built a caching layer", [], TAILOR, VERIFIER) is False
    llm.assert_not_called()


async def test_empty_tailored_text_is_refused(mocker):
    llm = mocker.patch("jobos.tailorer.entailment.acompletion")

    assert await verify_entailment("   ", EVIDENCE, TAILOR, VERIFIER) is False
    llm.assert_not_called()


async def test_verifier_is_asked_about_the_actual_claims(mocker):
    """The evidence must actually be sent — it was previously ignored entirely."""
    llm = mocker.patch("jobos.tailorer.entailment.acompletion", return_value=_verdict(True))

    await verify_entailment("Cut P99 latency 45%", EVIDENCE, TAILOR, VERIFIER)

    prompt = llm.call_args.kwargs["messages"][1]["content"]
    assert "Cut P99 latency 45%" in prompt
    assert "Redis caching layer" in prompt, "evidence must reach the verifier"
