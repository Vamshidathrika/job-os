"""Unit tests for Rule 14 Dual-Family Model Gate."""

import pytest
from jobos.tailorer import verify_entailment


@pytest.mark.asyncio
async def test_same_model_family_locks_to_band_c() -> None:
    """If tailor_provider and verifier_provider belong to the same model family, entailment returns False (Band C lockout)."""
    evidence = [{"id": "b1", "evidence_url": "https://example.com/proof1"}]
    # Groq (Llama) and NIM (Llama) resolve to same family 'llama'
    res = await verify_entailment(
        tailored_text="Built microservice",
        evidence_bullets=evidence,
        tailor_provider="groq",
        verifier_provider="nim",
    )
    assert res is False
