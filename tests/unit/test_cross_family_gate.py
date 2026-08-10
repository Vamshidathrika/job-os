"""Unit tests for Rule 14 Dual-Family Model Gate."""

import json

import pytest

from jobos.tailorer import verify_entailment

EVIDENCE = [{"id": "b1", "bullet_text": "Built a microservice", "evidence_url": "https://example.com/proof1"}]


def _entailed_verdict() -> dict:
    return {
        "choices": [
            {"message": {"content": json.dumps({"entailed": True, "unsupported_claims": []})}}
        ]
    }


@pytest.mark.asyncio
async def test_same_model_family_locks_to_band_c(mocker) -> None:
    """If tailor_provider and verifier_provider belong to the same model family, entailment returns False (Band C lockout)."""
    llm = mocker.patch("jobos.tailorer.entailment.acompletion")
    # Groq (Llama) and NIM (Llama) resolve to same family 'llama'
    res = await verify_entailment(
        tailored_text="Built microservice",
        evidence_bullets=EVIDENCE,
        tailor_provider="groq",
        verifier_provider="nim",
    )
    assert res is False
    llm.assert_not_called(), "must refuse before spending a verifier call"


@pytest.mark.asyncio
async def test_distinct_families_are_allowed_to_verify(mocker) -> None:
    mocker.patch("jobos.tailorer.entailment.acompletion", return_value=_entailed_verdict())

    res = await verify_entailment(
        tailored_text="Built microservice",
        evidence_bullets=EVIDENCE,
        tailor_provider="openrouter",  # 'mixed'
        verifier_provider="nim",  # 'llama'
    )
    assert res is True


@pytest.mark.asyncio
async def test_two_mixed_providers_fail_closed(mocker) -> None:
    """Both 'mixed' could resolve to the identical model, letting the verifier
    grade its own output. The old code explicitly exempted 'mixed' and passed."""
    llm = mocker.patch("jobos.tailorer.entailment.acompletion")

    res = await verify_entailment(
        tailored_text="Built microservice",
        evidence_bullets=EVIDENCE,
        tailor_provider="openrouter",
        verifier_provider="openrouter",
    )
    assert res is False
    llm.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_provider_fails_closed(mocker) -> None:
    llm = mocker.patch("jobos.tailorer.entailment.acompletion")

    res = await verify_entailment(
        tailored_text="Built microservice",
        evidence_bullets=EVIDENCE,
        tailor_provider="some-new-provider",
        verifier_provider="nim",
    )
    assert res is False
    llm.assert_not_called()
