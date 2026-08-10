"""Cross-family LLM entailment verifier module."""

from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion

from jobos.config import Settings, settings as default_settings
from jobos.vault.credentials import MODEL_FAMILIES

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a strict fact-checker for resume claims.

You receive CLAIMS (from a tailored resume) and EVIDENCE (the candidate's
verified achievements). Decide whether every claim is supported by the evidence.

A claim is supported ONLY if the evidence states it or directly implies it.
Treat these as NOT supported:
- any number, percentage, duration, headcount or amount that the evidence does
  not state (a claim may not be more specific or more impressive than its evidence)
- any employer, product, technology, award or title absent from the evidence
- any seniority or scope the evidence does not establish

Judge only the claims given. Do not use outside knowledge about the companies
or technologies involved.

Return ONLY JSON:
{"entailed": true|false, "unsupported_claims": ["<claim>", ...]}"""


async def verify_entailment(
    tailored_text: str,
    evidence_bullets: list[dict[str, Any]],
    tailor_provider: str,
    verifier_provider: str,
    settings: Settings | None = None,
) -> bool:
    """
    Checks every claim in tailored text against retrieved evidence.
    Rule 14 Check: if tailor and verifier belong to same model family,
    autonomous tailoring is REFUSED and returns False.

    This gate guards text that gets sent to employers, so it fails closed:
    an unreachable verifier, an unparseable reply, or missing evidence all
    return False. Only an explicit, parseable "entailed" verdict passes.

    Args:
        tailored_text: The tailored resume text.
        evidence_bullets: List of evidence bullet points.
        tailor_provider: Provider used for tailoring.
        verifier_provider: Provider used for verification.
        settings: Application settings; defaults to the global singleton.

    Returns:
        True if all claims are entailed, False otherwise.
    """
    settings = settings or default_settings

    if not _families_are_distinct(tailor_provider, verifier_provider):
        return False

    if not tailored_text.strip():
        logger.warning("entailment_refused_empty_text")
        return False

    if not evidence_bullets:
        # With no evidence, nothing can be entailed. Passing here would let
        # an unverified resume through whenever retrieval returned nothing.
        logger.warning("entailment_refused_no_evidence")
        return False

    logger.info("Verifying entailment of tailored resume against evidence bullets")

    try:
        response: Any = await acompletion(
            model=settings.llm.entailment_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(tailored_text, evidence_bullets)},
            ],
            temperature=0.0,
        )
        raw = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("entailment_verifier_unavailable", error=str(e))
        return False

    verdict = _parse_verdict(raw)
    if verdict is None:
        logger.error("entailment_verdict_unparseable")
        return False

    entailed, unsupported = verdict
    if not entailed:
        logger.warning("entailment_failed", unsupported_claims=unsupported)
        return False

    # A "yes" that still lists unsupported claims is self-contradictory;
    # trust the specific finding over the summary flag.
    if unsupported:
        logger.warning("entailment_contradictory_verdict", unsupported_claims=unsupported)
        return False

    logger.info("entailment_passed", evidence_count=len(evidence_bullets))
    return True


def _families_are_distinct(tailor_provider: str, verifier_provider: str) -> bool:
    """Whether tailoring and verification use genuinely different model families.

    Fails closed on unknown providers and on the 'mixed' family: 'mixed' means
    the concrete model is chosen per request (OpenRouter), so two 'mixed'
    providers could resolve to the very same model — which would make the
    verifier grade its own output.
    """
    tailor_family = MODEL_FAMILIES.get(tailor_provider)
    verifier_family = MODEL_FAMILIES.get(verifier_provider)

    if not tailor_family or not verifier_family:
        logger.warning(
            "Cross-family entailment refused: unknown provider family.",
            tailor_provider=tailor_provider,
            verifier_provider=verifier_provider,
        )
        return False

    if tailor_family == verifier_family:
        logger.warning(
            "Cross-family entailment failed: tailor and verifier use the same model family.",
            tailor_provider=tailor_provider,
            verifier_provider=verifier_provider,
            family=tailor_family,
        )
        return False

    return True


def _build_prompt(tailored_text: str, evidence_bullets: list[dict[str, Any]]) -> str:
    """Render the claims and the evidence they must be checked against."""
    evidence = [
        {
            "id": str(bullet.get("id", "")),
            "text": bullet.get("bullet_text") or bullet.get("text") or "",
            "metric": bullet.get("metric"),
            "company": bullet.get("company"),
        }
        for bullet in evidence_bullets
    ]
    return (
        "EVIDENCE (the only supported facts):\n"
        f"{json.dumps(evidence, indent=2)}\n\n"
        "CLAIMS (the tailored resume text):\n"
        f"{tailored_text.strip()}"
    )


def _parse_verdict(raw: str) -> tuple[bool, list[str]] | None:
    """Extract (entailed, unsupported_claims) from the verifier's reply."""
    text = str(raw).strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None

    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict) or not isinstance(payload.get("entailed"), bool):
        return None

    unsupported = payload.get("unsupported_claims")
    return payload["entailed"], [str(c) for c in unsupported] if isinstance(unsupported, list) else []
