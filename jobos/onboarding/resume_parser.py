"""Resume parser for the JOBOS onboarding flow."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog
from litellm import acompletion

from jobos.config import Settings, settings as default_settings

logger = structlog.get_logger(__name__)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){9,13}\d")

SYSTEM_PROMPT = """You extract structured data from resume text.

Rules:
- Use ONLY what appears in the text. Never infer or invent an employer, date, \
degree, or skill that is not written there.
- Leave a field empty (empty string or empty list) when the text does not \
contain it. An empty field is correct; a guessed one is not.

Return ONLY JSON:
{"name": "", "email": "", "phone": "",
 "education": [{"institution": "", "degree": "", "year": ""}],
 "experience": [{"company": "", "title": "", "start": "", "end": "", "bullets": [""]}],
 "skills": [""], "summary": ""}"""

EMPTY_RESUME: dict[str, Any] = {
    "name": "",
    "email": "",
    "phone": "",
    "education": [],
    "experience": [],
    "skills": [],
    "summary": "",
}


class UnsupportedResumeFormatError(ValueError):
    """Raised when the uploaded file is not a supported resume format."""


async def parse_uploaded_resume(
    file_path: str, settings: Settings | None = None
) -> dict[str, Any]:
    """
    Parse an uploaded resume and return structured data.

    Args:
        file_path (str): The path to the uploaded resume file (PDF or DOCX).
        settings: Application settings; defaults to the global singleton.

    Returns:
        dict[str, Any]: Structured resume data containing name, email, phone,
                        education, experience, skills, and summary.

    Raises:
        FileNotFoundError: if the file does not exist.
        UnsupportedResumeFormatError: if the extension is not supported.
    """
    settings = settings or default_settings
    logger.info("parsing_resume_start", file_path=file_path)

    text = extract_text(file_path)
    if not text.strip():
        logger.warning("resume_text_empty", file_path=file_path)
        return dict(EMPTY_RESUME)

    parsed = await _structure_with_llm(text, settings)
    if parsed is None:
        # Fall back to regex-extractable facts rather than returning invented
        # data: partial truth beats a confident fabrication downstream.
        logger.warning("resume_llm_parse_failed_using_regex_fallback", file_path=file_path)
        parsed = dict(EMPTY_RESUME)

    # Contact details are cheap to verify directly from the text, so trust the
    # regex over the model when the model missed them.
    if not parsed.get("email"):
        match = EMAIL_RE.search(text)
        parsed["email"] = match.group(0) if match else ""
    if not parsed.get("phone"):
        match = PHONE_RE.search(text)
        parsed["phone"] = match.group(0).strip() if match else ""

    logger.info(
        "parsing_resume_complete",
        file_path=file_path,
        experience_count=len(parsed.get("experience") or []),
        skills_count=len(parsed.get("skills") or []),
    )
    return parsed


def extract_text(file_path: str) -> str:
    """Extract raw text from a PDF, DOCX or plain-text resume."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Resume not found: {file_path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf_text(path)
    if suffix == ".docx":
        return _extract_docx_text(path)
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")

    raise UnsupportedResumeFormatError(
        f"Unsupported resume format {suffix!r}; expected .pdf, .docx or .txt"
    )


def _extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF via pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover - depends on install extras
        raise RuntimeError("pypdf is required to parse PDF resumes") from e

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx_text(path: Path) -> str:
    """Extract text from a DOCX via python-docx."""
    try:
        import docx
    except ImportError as e:  # pragma: no cover - depends on install extras
        raise RuntimeError("python-docx is required to parse DOCX resumes") from e

    document = docx.Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


async def _structure_with_llm(text: str, settings: Settings) -> dict[str, Any] | None:
    """Turn raw resume text into the structured schema, or None on failure."""
    try:
        response: Any = await acompletion(
            model=settings.llm.tailoring_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                # Long resumes are truncated: the tail is usually references
                # and boilerplate, and the cap bounds token cost per upload.
                {"role": "user", "content": text[:20000]},
            ],
            temperature=0.0,
        )
        raw = response["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("resume_structuring_failed", error=str(e))
        return None

    payload = _parse_json_object(raw)
    if payload is None:
        return None

    return {**EMPTY_RESUME, **{k: v for k, v in payload.items() if k in EMPTY_RESUME}}


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """Parse a JSON object out of a model reply, tolerating code fences."""
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
    return payload if isinstance(payload, dict) else None
