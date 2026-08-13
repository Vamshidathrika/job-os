"""Sequences scoring, EV and tiering over ingested jobs.

This is the glue between ingestion and the warm-path race. Every function it
calls already exists and is tested; this module only orders them and persists
the outcome.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from jobos.comp.predictor import predict_salary_band
from jobos.ingestion.embedder import generate_embedding
from jobos.matcher.ev_ranker import calculate_ev
from jobos.matcher.scorer import compute_requirement_match, compute_similarity
from jobos.matcher.tier_gate import classify_tier
from jobos.referral.network_mapper import map_existing_network

logger = structlog.get_logger(__name__)

# Similarity is a weak proxy for offer probability, so it is damped rather
# than used directly: a 0.8 cosine match is not an 80% chance of an offer.
P_OFFER_SCALE = 0.35

# Top of the cold-start comp ladder in comp/predictor.py (senior band, India).
# ev_score is expressed as a fraction of this, so a senior-band role scores
# near 1.0 and a junior one near 0.25.
COMP_REFERENCE_INR = 5_000_000.0

# Mirrors calculate_ev's default, so both scales agree on how likely an offer
# is to be accepted.
DEFAULT_P_ACCEPT = 0.85

# classify_tier(match_score, ev_score) weighs match quality and opportunity
# value as two INDEPENDENT dimensions. ev_score must therefore not re-embed
# match_score. Deriving it from expected value would do exactly that —
# EV = p_offer x comp x p_accept, and p_offer is itself match_score damped by
# P_OFFER_SCALE — which both double-counts the match and caps ev_score at
# 0.35, below the gate's 0.60. Tier 1 was unreachable and the warm-path race,
# which only fires on Tier 1, could never start. So ev_score measures the
# value dimension alone: expected comp, normalised. Raw EV is still computed
# and stored for ranking, which is what it is actually good for.


def _skills_from_bullets(bullets: list[dict[str, Any]]) -> list[str]:
    """Every distinct word/phrase in bullet text — a coarse but real skill
    surface, since there is no dedicated skills table yet (see the matching
    relevance plan's Step 1 note on job_requirements being unwritten schema
    for the same underlying reason: no extraction step existed)."""
    text = " ".join(b.get("bullet_text") or "" for b in bullets)
    return [w.strip(",.():;") for w in text.split() if w.strip(",.():;")]


def build_profile_text(bullets: list[dict[str, Any]]) -> str:
    """Flatten the Career Graph into one document for embedding."""
    parts: list[str] = []
    for bullet in bullets:
        role = bullet.get("role") or ""
        company = bullet.get("company") or ""
        text = bullet.get("bullet_text") or ""
        parts.append(" ".join(p for p in (role, company, text) if p))
    return "\n".join(parts)


async def run_matching(conn: Any, user_id: str, limit: int = 500) -> dict[str, int]:
    """Score every ingested job against the user's Career Graph.

    Args:
        conn: A tenant-scoped connection.
        user_id: The user to match for.
        limit: Maximum jobs to score in one pass.

    Returns:
        Counts of jobs scored and how many landed in Tier 1.
    """
    bullets = [
        dict(row)
        for row in await conn.fetch(
            "SELECT bullet_text, role, company FROM cg_bullets WHERE user_id = $1::uuid",
            user_id,
        )
    ]
    if not bullets:
        logger.warning("matching_skipped_no_career_graph", user_id=user_id)
        return {"scored": 0, "tier_1": 0}

    profile_text = build_profile_text(bullets)
    profile_vector = await generate_embedding(profile_text)

    jobs = await conn.fetch(
        """
        SELECT j.id, j.title, j.description, j.location, j.embedding, c.name AS company_name
          FROM jobs j
          LEFT JOIN companies c ON c.id = j.company_id
         WHERE j.embedding IS NOT NULL
         ORDER BY j.first_seen_at DESC
         LIMIT $1
        """,
        limit,
    )

    # Warm-contact detection is computed once for the whole run (pure
    # in-memory fuzzy matching, no new I/O per job) rather than per-job in
    # the loop below — see docs/superpowers/plans/
    # 2026-08-12-matching-relevance-fixes.md Task 2 for why: referred
    # applicants convert 4-10x better than cold applies, so classify_tier
    # needs to know which jobs have a real warm connection at the company.
    contacts = [
        dict(row)
        for row in await conn.fetch(
            "SELECT full_name, company_domain, email, title, source FROM people WHERE user_id = $1::uuid",
            user_id,
        )
    ]
    company_names = list({j["company_name"] for j in jobs if j["company_name"]})
    warm_leads = (
        await map_existing_network(
            [{**c, "company": c["company_domain"]} for c in contacts], company_names
        )
        if contacts and company_names
        else []
    )
    # map_existing_network's FUZZY_MATCH_THRESHOLD (0.5) is tuned for outreach
    # discovery (jobos/runner/warm_paths.py), where a fuzzy false positive
    # just wastes an outreach attempt — cheap. Tiering is different: a false
    # positive here promotes a job to Tier 1 and can defer a cold application
    # by up to 7 days waiting on a referral that doesn't actually exist. So
    # for has_warm_contact specifically, require an exact core-name match
    # (match_score == 1.0 — see network_mapper._similarity's fast path)
    # rather than the general fuzzy threshold. This does not change
    # map_existing_network itself or its threshold, so warm_paths.py's
    # existing fuzzy-matching behavior for outreach discovery is untouched.
    exact_warm_leads = [w for w in warm_leads if w.get("match_score") == 1.0]
    warm_companies = {w["matched_target_company"] for w in exact_warm_leads if w.get("email")}

    scored = tier_1 = 0
    for job in jobs:
        job_vector = _parse_vector(job["embedding"])
        if not job_vector:
            continue

        score = compute_similarity(job_vector, profile_vector)
        band = predict_salary_band(
            title=job["title"] or "", location=job["location"] or "", yoe=_years_of_experience(bullets)
        )
        # Raw EV drives ranking (what is this opportunity worth overall).
        ev = calculate_ev(p_offer=score * P_OFFER_SCALE, predicted_comp_p50=band["p50"])
        # ev_score drives tiering, and measures value only — see the note on
        # COMP_REFERENCE_INR for why it must not re-embed match_score.
        ev_score = min(1.0, (band["p50"] * DEFAULT_P_ACCEPT) / COMP_REFERENCE_INR)
        tier = classify_tier(
            match_score=score,
            ev_score=ev_score,
            has_warm_contact=job["company_name"] in warm_companies,
        )

        hard_reqs_raw = await conn.fetchval(
            "SELECT hard_reqs FROM job_requirements WHERE job_id = $1", job["id"]
        )
        hard_reqs = json.loads(hard_reqs_raw) if hard_reqs_raw else []
        candidate_skills = _skills_from_bullets(bullets)
        coverage, missing = compute_requirement_match(hard_reqs, candidate_skills)

        await conn.execute(
            """
            INSERT INTO matches (id, user_id, job_id, score, ev_score, tier, skill_coverage, missing_skills)
            VALUES (gen_random_uuid(), $1::uuid, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (user_id, job_id) DO UPDATE
                SET score = EXCLUDED.score,
                    ev_score = EXCLUDED.ev_score,
                    tier = EXCLUDED.tier,
                    skill_coverage = EXCLUDED.skill_coverage,
                    missing_skills = EXCLUDED.missing_skills
            """,
            user_id,
            job["id"],
            score,
            ev_score,
            tier,
            coverage,
            json.dumps(missing),
        )
        scored += 1
        if tier == 1:
            tier_1 += 1

    logger.info("matching_complete", user_id=user_id, scored=scored, tier_1=tier_1)
    return {"scored": scored, "tier_1": tier_1}


def _parse_vector(raw: Any) -> list[float]:
    """pgvector comes back as a string like '[0.1,0.2]'."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [float(v) for v in raw]
    text = str(raw).strip().strip("[]")
    if not text:
        return []
    return [float(part) for part in text.split(",")]


def _years_of_experience(bullets: list[dict[str, Any]]) -> int:
    """Coarse seniority proxy: distinct employers in the Career Graph.

    A real estimate needs position dates, which the importer records but the
    bullets table does not carry; this keeps comp banding stable until then.
    """
    companies = {b.get("company") for b in bullets if b.get("company")}
    return max(1, len(companies) * 2)
