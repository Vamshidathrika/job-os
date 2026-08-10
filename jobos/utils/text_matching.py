"""Shared text normalization and fuzzy matching utilities."""

from __future__ import annotations

import re
import structlog

logger = structlog.get_logger(__name__)


def normalize_text(text: str) -> str:
    """Normalize text by converting to lowercase, stripping punctuation and extra whitespace."""
    if not text:
        return ""
    text = text.lower().replace("_", " ")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def compute_fuzzy_similarity(str1: str, str2: str) -> float:
    """Compute token overlap similarity ratio between two strings (0.0 to 1.0)."""
    tokens1 = set(normalize_text(str1).split())
    tokens2 = set(normalize_text(str2).split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def match_field_to_user_data(field_label: str, user_data: dict[str, str], threshold: float = 0.4) -> str | None:
    """Find best matching user data key for a given form field label using fuzzy token matching."""
    norm_label = normalize_text(field_label)
    best_match: str | None = None
    best_score = 0.0

    for key, value in user_data.items():
        score = compute_fuzzy_similarity(norm_label, key)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = value

    return best_match
