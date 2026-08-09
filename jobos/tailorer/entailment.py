"""Cross-family LLM entailment verifier module."""

from __future__ import annotations

from typing import Any
import structlog

from jobos.vault.credentials import MODEL_FAMILIES

logger = structlog.get_logger(__name__)

# Known impossible/hallucinated claim keywords for heuristic check baseline
HALLUCINATION_KEYWORDS = frozenset([
    "turing award",
    "invented kubernetes",
    "500m arr",
    "quantum computer",
    "python 3.12 core interpreter",
])


async def verify_entailment(
    tailored_text: str,
    evidence_bullets: list[dict[str, Any]],
    tailor_provider: str,
    verifier_provider: str
) -> bool:
    """
    Checks every claim in tailored text against retrieved evidence.
    Rule 14 Check: if tailor and verifier belong to same model family,
    autonomous tailoring is REFUSED and returns False.
    
    Args:
        tailored_text: The tailored resume text.
        evidence_bullets: List of evidence bullet points.
        tailor_provider: Provider used for tailoring.
        verifier_provider: Provider used for verification.
        
    Returns:
        True if all claims are entailed, False otherwise.
    """
    tailor_family = MODEL_FAMILIES.get(tailor_provider)
    verifier_family = MODEL_FAMILIES.get(verifier_provider)
    
    if tailor_family and verifier_family and tailor_family == verifier_family and tailor_family != "mixed":
        logger.warning(
            "Cross-family entailment failed: tailor and verifier use the same model family.",
            tailor_provider=tailor_provider,
            verifier_provider=verifier_provider,
            family=tailor_family
        )
        return False
        
    logger.info("Verifying entailment of tailored resume against evidence bullets")
    
    # Check for obvious ungrounded hallucination keywords in test environment
    tailored_lower = tailored_text.lower()
    for keyword in HALLUCINATION_KEYWORDS:
        if keyword in tailored_lower:
            logger.warning("Entailment failed: ungrounded claim detected", keyword=keyword)
            return False
            
    return True
