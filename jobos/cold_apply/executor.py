"""Playwright-based form filler for cold-apply preparation.

Scope, stated explicitly: this fills out a real application form and takes a
screenshot for human review. It never clicks a submit control, on any page,
under any circumstance — including after a human approves it in the
dashboard. Finishing the actual submission is the operator's own action, in
their own browser. Auto-submitting on approval would just move the same
live-form-automation risk one step later; the artifact this produces (filled
fields + screenshot) is the deliverable, not a click.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from playwright.async_api import async_playwright

from jobos.cold_apply.screenshot import capture_submission_screenshot
from jobos.utils.text_matching import match_field_to_user_data

logger = structlog.get_logger(__name__)

DEFAULT_SCREENSHOT_DIR = Path("/tmp/jobos_cold_apply_screenshots")


class ColdApplyExecutor:
    """Fills a real application form and prepares it for human review."""

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
        self, job_url: str, resume_path: str | None, answers: dict[str, str]
    ) -> dict[str, Any]:
        """
        Fill out a real application form using fuzzy field matching.

        Opens job_url in a real (headless) browser, reads each labelled
        input/select/textarea inside the page's <form>, matches it to
        `answers` via fuzzy label matching, fills it, attaches the resume
        file if a file input exists, and screenshots the result. Never
        clicks anything resembling a submit control.

        Args:
            job_url: URL (or local file:// path, for testing) of the
                application page.
            resume_path: Path to the resume file to attach, or None to skip
                the file upload.
            answers: The candidate's answers, keyed by topic (e.g.
                "first name", "email") for fuzzy matching against form labels.

        Returns:
            Dict with fields_filled (count), filled (label -> value actually
            written), unmatched_labels (fields no answer was found for), and
            screenshot_path (a real file that was actually written).
        """
        self.logger.info("filling_application", job_url=job_url)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page()
                await page.goto(job_url)

                fields = await self._read_form_fields(page)
                form_labels = [f["label"] for f in fields]
                mapped = self.map_answers_to_fields(form_labels, answers)

                filled: dict[str, str] = {}
                for field in fields:
                    value = mapped.get(field["label"])
                    if value is None:
                        continue
                    await self._fill_field(page, field, value)
                    filled[field["label"]] = value

                if resume_path:
                    await self._attach_resume(page, resume_path)

                DEFAULT_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
                screenshot_path = str(
                    DEFAULT_SCREENSHOT_DIR / f"{self.tenant_id}-{_safe_slug(job_url)}.png"
                )
                await capture_submission_screenshot(page, screenshot_path)

                result = {
                    "fields_filled": len(filled),
                    "filled": filled,
                    "unmatched_labels": [lbl for lbl in form_labels if lbl not in filled],
                    "screenshot_path": screenshot_path,
                }
                self.logger.info(
                    "application_filled",
                    fields_filled=result["fields_filled"],
                    screenshot_path=screenshot_path,
                )
                return result
            finally:
                await browser.close()

    async def submit_application(
        self, job_url: str, resume_path: str | None = None, answers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """
        Prepare an application for human review. Never submits it.

        This performs the exact same fill-and-screenshot flow as
        fill_application and returns a dry_run result describing what a
        human would see if they finished submitting it themselves. No
        Playwright action in this method — or anywhere in this class —
        clicks a submit-like control on any page, real or local.

        Returns:
            Dict identical in shape to fill_application's result, plus
            {"status": "prepared_for_review", "dry_run": True}.
        """
        self.logger.info("preparing_application_for_review", job_url=job_url)
        result = await self.fill_application(job_url, resume_path, answers or {})
        return {**result, "status": "prepared_for_review", "dry_run": True}

    async def _read_form_fields(self, page: Any) -> list[dict[str, Any]]:
        """Read every labelled input/select/textarea inside the page's form."""
        elements = await page.locator(
            "form input:not([type=hidden]):not([type=submit]):not([type=checkbox]), "
            "form select, form textarea"
        ).all()

        fields = []
        for element in elements:
            name = await element.get_attribute("name")
            input_type = await element.get_attribute("type") or "text"
            if not name:
                continue
            label = await self._label_for(page, name)
            fields.append({"name": name, "type": input_type, "label": label or name})
        return fields

    async def _label_for(self, page: Any, field_name: str) -> str | None:
        """Find the visible <label> text for a field by its name attribute."""
        label_locator = page.locator(f"label:has(input[name='{field_name}']), "
                                      f"label:has(select[name='{field_name}'])")
        if await label_locator.count() == 0:
            return None
        text = await label_locator.first.inner_text()
        return text.strip()

    async def _fill_field(self, page: Any, field: dict[str, Any], value: str) -> None:
        """Fill one field by its real name attribute, respecting its type."""
        name, field_type = field["name"], field["type"]
        if field_type == "file":
            return  # handled separately by _attach_resume
        if field["name"] and await page.locator(f"select[name='{name}']").count() > 0:
            await page.locator(f"select[name='{name}']").select_option(label=value)
        else:
            await page.locator(f"[name='{name}']").fill(value)

    async def _attach_resume(self, page: Any, resume_path: str) -> None:
        """Attach the resume file to the form's file input, if one exists."""
        file_input = page.locator("input[type=file][name='resume']")
        if await file_input.count() > 0:
            await file_input.set_input_files(resume_path)


def _safe_slug(text: str) -> str:
    """Filesystem-safe fragment of a URL for use in a screenshot filename."""
    return "".join(c if c.isalnum() else "_" for c in text)[-40:]
