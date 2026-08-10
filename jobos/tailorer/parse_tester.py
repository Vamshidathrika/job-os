"""ATS parse fidelity checker module."""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){9,13}\d")
TOKEN_RE = re.compile(r"[a-z0-9+#.]+")

# Headings an ATS keys on to segment a resume. Losing one usually means the
# parser drops or misattributes everything beneath it.
SECTION_HEADINGS = (
    "experience",
    "education",
    "skills",
    "projects",
    "summary",
    "certifications",
)

# Weights sum to 1.0.
CONTACT_WEIGHT = 0.4
SECTION_WEIGHT = 0.3
CONTENT_WEIGHT = 0.3


def evaluate_parse_fidelity(original_resume: str, tailored_resume: str) -> float:
    """
    Calculates re-parse fidelity score.

    Measures whether tailoring preserved the things an ATS relies on to read a
    resume: reachable contact details, recognisable section headings, and the
    substantive vocabulary of the original. It is a structural proxy, not a
    simulation of any particular ATS — but unlike a constant it can actually
    fail, which is the point of a fidelity gate.

    Args:
        original_resume: Original parsed resume text.
        tailored_resume: Tailored resume text.

    Returns:
        A score from 0.0 to 1.0 indicating parse fidelity.
    """
    logger.info("Evaluating ATS parse fidelity")

    if not original_resume.strip() or not tailored_resume.strip():
        logger.warning("parse_fidelity_empty_input")
        return 0.0

    contact = _contact_retention(original_resume, tailored_resume)
    sections = _section_retention(original_resume, tailored_resume)
    content = _content_retention(original_resume, tailored_resume)

    score = CONTACT_WEIGHT * contact + SECTION_WEIGHT * sections + CONTENT_WEIGHT * content
    score = round(max(0.0, min(1.0, score)), 4)

    logger.info(
        "parse_fidelity_evaluated",
        score=score,
        contact=contact,
        sections=sections,
        content=content,
    )
    return score


def _contact_retention(original: str, tailored: str) -> float:
    """Share of contact identifiers that survived tailoring.

    A resume that loses its email address is unreachable no matter how well
    it reads, so this carries the heaviest weight.
    """
    checks = []
    for pattern in (EMAIL_RE, PHONE_RE):
        found = set(pattern.findall(original))
        if found:
            checks.append(bool(found & set(pattern.findall(tailored))))

    if not checks:
        # Nothing to preserve — do not penalise for what was never there.
        return 1.0
    return sum(checks) / len(checks)


def _section_retention(original: str, tailored: str) -> float:
    """Share of the original's section headings still present."""
    original_lower, tailored_lower = original.lower(), tailored.lower()
    present = [h for h in SECTION_HEADINGS if h in original_lower]

    if not present:
        return 1.0
    return sum(h in tailored_lower for h in present) / len(present)


def _content_retention(original: str, tailored: str) -> float:
    """How much of the original's vocabulary the tailored version keeps.

    Tailoring legitimately drops irrelevant material, so this is a retention
    ratio rather than a similarity: it asks how much of the tailored text is
    grounded in the original, which also surfaces wholesale invention.
    """
    original_tokens = set(TOKEN_RE.findall(original.lower()))
    tailored_tokens = set(TOKEN_RE.findall(tailored.lower()))

    if not tailored_tokens:
        return 0.0
    return len(tailored_tokens & original_tokens) / len(tailored_tokens)
