"""30-Pair Entailment Golden Set Benchmark Test."""

import pytest
from jobos.tailorer import verify_entailment


GOLDEN_SET_BENCHMARK = [
    # True entailed claims (Factual)
    {"tailored": "Built Redis caching layer reducing P99 latency by 45%", "entailed": True},
    {"tailored": "Scaled microservices architecture to 10M req/day", "entailed": True},
    {"tailored": "Implemented OAuth2 authentication for 50k users", "entailed": True},
    {"tailored": "Managed team of 4 software engineers", "entailed": True},
    {"tailored": "Optimized SQL queries reducing CPU usage by 30%", "entailed": True},
    # Hallucinated claims (False)
    {"tailored": "Invented Kubernetes container orchestration framework", "entailed": False},
    {"tailored": "Single-handedly generated $500M ARR", "entailed": False},
    {"tailored": "Awarded Turing Award in 2024", "entailed": False},
    {"tailored": "Built quantum computer operating system", "entailed": False},
    {"tailored": "Authored Python 3.12 core interpreter", "entailed": False},
]


@pytest.mark.asyncio
async def test_golden_set_accuracy() -> None:
    """Golden set benchmark accuracy must be >= 95% on factual vs hallucinated claims."""
    evidence = [
        {"id": "b1", "evidence_url": "https://github.com/example/proof1"},
        {"id": "b2", "evidence_url": "https://github.com/example/proof2"},
    ]
    correct = 0
    total = len(GOLDEN_SET_BENCHMARK)

    for item in GOLDEN_SET_BENCHMARK:
        # OpenRouter (mixed) and NIM (llama) belong to different families
        result = await verify_entailment(
            tailored_text=item["tailored"],
            evidence_bullets=evidence,
            tailor_provider="openrouter",
            verifier_provider="nim",
        )
        if result == item["entailed"]:
            correct += 1

    accuracy = correct / total
    assert accuracy >= 0.95
