"""Playwright-based form filler."""

from __future__ import annotations

from typing import Any

import structlog

from jobos.utils.text_matching import match_field_to_user_data

logger = structlog.get_logger(__name__)

# What a real implementation still needs before it can submit anything:
#   - the `playwright` extra installed and browsers provisioned
#   - per-ATS form strategies (Greenhouse/Lever/Ashby/Workday render very
#     different DOMs), including file upload and multi-page flows
#   - a screenshot/artifact store so submissions are auditable
_NOT_IMPLEMENTED_MESSAGE = (
    "Cold apply browser automation is not implemented. Submitting requires a "
    "real Playwright session against the ATS form; returning a success status "
    "without one would record applications that were never sent."
)


class ColdApplyExecutor:
    """Executes cold application submissions using Playwright."""

    def __init__(self, tenant_id: str):
        """
        Initialize the executor.

        Args:
            tenant_id: The tenant identifier executing the application.
        """
        self.tenant_id = tenant_id
        self.logger = logger.bind(tenant_id=tenant_id)

    def map_answers_to_fields(
        self, form_labels: list[str], user_data: dict[str, str]
    ) -> dict[str, str]:
        """Match a form's field labels to the user's stored answers.

        This is the one piece that is genuinely implemented and independently
        useful: given the labels scraped from a form, decide which of the
        user's values belongs in each. It performs no browser work.

        Args:
            form_labels: Labels read off the application form.
            user_data: The user's answers, keyed by question/topic.

        Returns:
            Mapping of form label to the chosen answer, omitting labels with
            no confident match.
        """
        mapped: dict[str, str] = {}
        for label in form_labels:
            value = match_field_to_user_data(label, user_data)
            if value is not None:
                mapped[label] = value

        self.logger.info(
            "mapped_form_fields", total=len(form_labels), matched=len(mapped)
        )
        return mapped

    async def fill_application(
        self, job_url: str, resume_path: str, answers: dict[str, str]
    ) -> dict[str, Any]:
        """
        Fill out application form fields using fuzzy field matching.

        Raises:
            NotImplementedError: always. The previous version reported
                "filled" without ever loading job_url or uploading
                resume_path, so callers believed a form had been completed.
        """
        self.logger.error("cold_apply_fill_not_implemented", job_url=job_url)
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)

    async def submit_application(self, job_url: str, dry_run: bool = True) -> dict[str, Any]:
        """
        Submit (or dry-run) the application.

        Raises:
            NotImplementedError: always. The previous version returned
                {"status": "success"} plus a screenshot path that was never
                written — the system would mark a job as applied-to while the
                candidate had in fact never applied.
        """
        self.logger.error(
            "cold_apply_submit_not_implemented", job_url=job_url, dry_run=dry_run
        )
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)
