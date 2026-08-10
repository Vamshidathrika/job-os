"""Keyword extraction from job descriptions."""
from __future__ import annotations

import re
from collections import Counter

import structlog

logger = structlog.get_logger(__name__)

# Words that appear in nearly every job description and carry no signal about
# which skills a profile is missing.
STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or our that the
    to with will you your we they this these those role job work team looking need
    needed strong experience years year plus must should who what where when how
    about across into over under more most other new using use used help build
    building including etc via able ability good great excellent required preferred
    responsibilities requirements qualifications candidate candidates someone
    developer engineer engineering""".split()
)

# Multi-word skills that must not be split into meaningless unigrams.
KNOWN_PHRASES = (
    "system design",
    "machine learning",
    "deep learning",
    "data engineering",
    "distributed systems",
    "computer science",
    "test driven development",
    "ci cd",
)

TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
MIN_TOKEN_LENGTH = 2


def extract_target_keywords(job_descriptions: list[str]) -> dict[str, float]:
    """
    Extract and score target keywords from a list of job descriptions.

    WHAT: Parses text to find frequently occurring hard skills, tools, and domain terms.
    WHY: To identify keyword gaps in the user's profile so they can optimize for ATS and recruiters.

    Scores are document frequency: the share of the supplied descriptions that
    mention the term. A term in every JD scores 1.0, so the ranking reflects
    how broadly a skill is demanded rather than how often one verbose posting
    happens to repeat it.
    """
    logger.info("extracting_keywords", num_descriptions=len(job_descriptions))

    if not job_descriptions:
        return {}

    document_frequency: Counter[str] = Counter()
    for description in job_descriptions:
        # A term counts once per description, however often it is repeated.
        document_frequency.update(_terms_in(description))

    total_docs = len(job_descriptions)
    keywords = {
        term: round(count / total_docs, 4)
        for term, count in document_frequency.most_common()
    }
    logger.info("keywords_extracted", count=len(keywords))
    return keywords


def _terms_in(description: str) -> set[str]:
    """Distinct meaningful terms in one description, phrases included."""
    text = (description or "").lower()
    terms: set[str] = set()

    for phrase in KNOWN_PHRASES:
        if phrase in text:
            terms.add(phrase)
            # Drop the phrase so its parts don't also score as unigrams.
            text = text.replace(phrase, " ")

    for token in TOKEN_RE.findall(text):
        token = token.strip(".")
        if len(token) < MIN_TOKEN_LENGTH or token in STOPWORDS or token.isdigit():
            continue
        terms.add(token)

    return terms
