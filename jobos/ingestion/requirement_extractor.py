"""Pulls hard requirements out of a job description via LLM.

job_requirements.hard_reqs has existed in the schema since the first
migration but nothing ever wrote to it — this is that writer. Failure
returns [] rather than a guess: an empty requirements list just means
compute_requirement_match treats the job as having no hard gate, not that
the job is lying about needing a skill it doesn't.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from litellm import acompletion

logger = structlog.get_logger(__name__)

_PROMPT = """Extract the hard (must-have) technical requirements from this \
job description. Return ONLY JSON: {{"hard_requirements": ["skill1", "skill2"]}}. \
If there are none, return {{"hard_requirements": []}}.

Job description:
{description}
"""

# Job descriptions can run long; the extraction only needs the requirements
# section, so truncate rather than spend tokens (and latency) on the rest.
_MAX_DESCRIPTION_CHARS = 4000


async def extract_hard_requirements(job_description: str, settings: Any) -> list[str]:
    """Ask the model for the must-have skills in a job description.

    Returns [] on any failure — missing network/API access, a malformed or
    non-JSON reply, or an empty description — rather than raising, since a
    failed extraction should not block job ingestion (see poller.py) or be
    mistaken for "this job genuinely has no hard requirements".
    """
    if not job_description or not job_description.strip():
        return []
    try:
        response = await acompletion(
            model=settings.llm.tailoring_model,
            messages=[
                {
                    "role": "user",
                    "content": _PROMPT.format(description=job_description[:_MAX_DESCRIPTION_CHARS]),
                }
            ],
            api_key=settings.llm.platform_groq_key or None,
            temperature=0.0,
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        reqs = parsed.get("hard_requirements", [])
        return [str(r) for r in reqs if str(r).strip()]
    except Exception as e:
        logger.warning("requirement_extraction_failed", error=str(e))
        return []
