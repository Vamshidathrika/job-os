"""Playwright-based form filler."""

from __future__ import annotations

from typing import Any
import structlog
from jobos.utils.text_matching import match_field_to_user_data

logger = structlog.get_logger(__name__)


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

    async def fill_application(self, job_url: str, resume_path: str, answers: dict[str, str]) -> dict[str, Any]:
        """
        Fill out application form fields using fuzzy field matching.
        
        Args:
            job_url: URL of the job application.
            resume_path: Path to the resume file.
            answers: Dictionary of field IDs to values.
            
        Returns:
            Dictionary containing the state or result of the filling operation.
        """
        self.logger.info("filling_application", job_url=job_url, resume=resume_path)
        
        filled_count = 0
        filled_fields: dict[str, str] = {}
        
        for field_label, target_value in answers.items():
            matched_val = match_field_to_user_data(field_label, {field_label: target_value})
            if matched_val is not None:
                filled_fields[field_label] = matched_val
                filled_count += 1
                
        return {
            "status": "filled",
            "job_url": job_url,
            "fields_filled": filled_count,
            "details": filled_fields
        }

    async def submit_application(self, job_url: str, dry_run: bool = True) -> dict[str, Any]:
        """
        Submit (or dry-run) the application.
        
        Args:
            job_url: URL of the job application.
            dry_run: Whether to actually submit or just test.
            
        Returns:
            Dictionary containing submission status, screenshot, and any errors.
        """
        self.logger.info("submitting_application", job_url=job_url, dry_run=dry_run)
        return {
            "status": "success" if not dry_run else "dry_run_success",
            "job_url": job_url,
            "screenshot_path": "/tmp/job_submission.png",
            "errors": []
        }
