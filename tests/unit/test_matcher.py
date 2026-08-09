"""Unit tests for Matcher and EV Ranker."""

import pytest
from jobos.matcher import (
    compute_similarity,
    compute_requirement_match,
    classify_tier,
    calculate_ev,
    rank_jobs_by_ev,
)


def test_compute_similarity() -> None:
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [1.0, 0.0, 0.0]
    vec3 = [0.0, 1.0, 0.0]
    assert compute_similarity(vec1, vec2) == pytest.approx(1.0)
    assert compute_similarity(vec1, vec3) == pytest.approx(0.0)


def test_compute_requirement_match() -> None:
    hard_reqs = ["Python", "PostgreSQL", "Kubernetes"]
    candidate_skills = ["Python", "PostgreSQL", "Docker"]
    coverage, gaps = compute_requirement_match(hard_reqs, candidate_skills)
    assert coverage == pytest.approx(2 / 3)
    assert "Kubernetes" in gaps


def test_classify_tier() -> None:
    assert classify_tier(match_score=0.70, ev_score=0.65) == 1
    assert classify_tier(match_score=0.55, ev_score=0.40) == 2
    assert classify_tier(match_score=0.30, ev_score=0.20) == 3


def test_calculate_ev() -> None:
    # EV = P(offer) * comp * P(accept)
    ev = calculate_ev(p_offer=0.40, predicted_comp_p50=3_000_000, p_accept=0.85)
    assert ev == 0.40 * 3_000_000 * 0.85


def test_rank_jobs_by_ev() -> None:
    jobs = [
        {"job_id": "j1", "ev_score": 100.0},
        {"job_id": "j2", "ev_score": 500.0},
        {"job_id": "j3", "ev_score": 250.0},
    ]
    ranked = rank_jobs_by_ev(jobs)
    assert ranked[0]["job_id"] == "j2"
    assert ranked[1]["job_id"] == "j3"
    assert ranked[2]["job_id"] == "j1"
