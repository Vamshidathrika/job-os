"""Onboarding wizard for new JOBOS tenants."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class OnboardingWizard:
    """Manages the onboarding flow for a tenant."""

    def __init__(self, tenant_id: str) -> None:
        """
        Initialize the onboarding wizard for a tenant.

        Args:
            tenant_id (str): The unique identifier for the tenant.
        """
        self.tenant_id = tenant_id
        self.steps = [
            "resume_upload",
            "target_roles",
            "target_companies",
            "location_preferences",
            "salary_expectations",
            "integration_setup",
        ]
        self.completed_steps: set[str] = set()
        logger.info("wizard_initialized", tenant_id=tenant_id)

    async def start(self) -> dict[str, Any]:
        """
        Begin the onboarding process.

        Returns:
            dict[str, Any]: The initial state of the onboarding wizard.
        """
        logger.info("wizard_started", tenant_id=self.tenant_id)
        return await self.get_progress()

    async def submit_step(self, step_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """
        Submit data for a specific onboarding step.

        Args:
            step_name (str): The name of the step being submitted.
            data (dict[str, Any]): The data provided for the step.

        Returns:
            dict[str, Any]: The updated progress of the onboarding wizard.
        """
        if step_name not in self.steps:
            logger.warning("invalid_step_submitted", tenant_id=self.tenant_id, step=step_name)
            raise ValueError(f"Invalid step: {step_name}")

        self.completed_steps.add(step_name)
        logger.info("step_submitted", tenant_id=self.tenant_id, step=step_name)
        
        # Add logic here to process and store data based on the step_name

        return await self.get_progress()

    async def get_progress(self) -> dict[str, Any]:
        """
        Get the current progress of the onboarding wizard.

        Returns:
            dict[str, Any]: A dictionary containing completed_steps, pending_steps, and percent_complete.
        """
        completed = list(self.completed_steps)
        pending = [step for step in self.steps if step not in self.completed_steps]
        percent_complete = (len(completed) / len(self.steps)) * 100 if self.steps else 100.0

        progress = {
            "completed_steps": completed,
            "pending_steps": pending,
            "percent_complete": percent_complete,
        }
        
        logger.debug("progress_fetched", tenant_id=self.tenant_id, percent_complete=percent_complete)
        return progress
