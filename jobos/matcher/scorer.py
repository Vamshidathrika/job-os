"""Scorer module for Job Matching."""

from __future__ import annotations

import math
import structlog

logger = structlog.get_logger(__name__)

def compute_similarity(job_embedding: list[float], profile_embedding: list[float]) -> float:
    """
    Computes the cosine similarity between two embeddings.
    
    Args:
        job_embedding: The job description embedding vector.
        profile_embedding: The candidate profile embedding vector.
        
    Returns:
        float: Cosine similarity score between 0.0 and 1.0.
    """
    if not job_embedding or not profile_embedding:
        logger.warning("Empty embeddings provided to compute_similarity")
        return 0.0
        
    if len(job_embedding) != len(profile_embedding):
        logger.warning("Embedding dimension mismatch", job_dim=len(job_embedding), profile_dim=len(profile_embedding))
        return 0.0

    dot_product = sum(a * b for a, b in zip(job_embedding, profile_embedding))
    norm_job = math.sqrt(sum(a * a for a in job_embedding))
    norm_profile = math.sqrt(sum(b * b for b in profile_embedding))
    
    if norm_job == 0.0 or norm_profile == 0.0:
        return 0.0
        
    similarity = dot_product / (norm_job * norm_profile)
    # Clamp between 0.0 and 1.0
    return max(0.0, min(1.0, similarity))


def compute_requirement_match(hard_reqs: list[str], candidate_skills: list[str]) -> tuple[float, list[str]]:
    """
    Calculates skill coverage fraction and identifies missing requirements.
    
    Args:
        hard_reqs: List of hard requirements for the job.
        candidate_skills: List of skills possessed by the candidate.
        
    Returns:
        tuple[float, list[str]]: A tuple containing the coverage fraction (0.0 to 1.0)
        and a list of missing requirements.
    """
    if not hard_reqs:
        return 1.0, []
        
    # Simple case-insensitive matching
    candidate_skills_lower = {skill.strip().lower() for skill in candidate_skills}
    missing_reqs = []
    
    for req in hard_reqs:
        req_lower = req.strip().lower()
        if req_lower not in candidate_skills_lower:
            missing_reqs.append(req)
            
    coverage_fraction = (len(hard_reqs) - len(missing_reqs)) / len(hard_reqs)
    
    logger.debug(
        "Computed requirement match",
        coverage_fraction=coverage_fraction,
        missing_count=len(missing_reqs)
    )
    
    return coverage_fraction, missing_reqs
