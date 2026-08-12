"""Screenshot capture for audit trail."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def capture_submission_screenshot(page: Any, output_path: str) -> str:
    """
    Captures and saves a screenshot of the application page.

    Args:
        page: A live Playwright Page to screenshot.
        output_path: Destination path for the screenshot.

    Returns:
        The path where the screenshot was actually saved.

    Raises:
        Whatever Playwright raises on a genuine capture failure — this must
        never return a path to a file that was not actually written, or the
        review flow would show a human a "screenshot" that doesn't exist.
    """
    logger.info("capturing_screenshot", output_path=output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=output_path, full_page=True)
    logger.info("screenshot_captured", output_path=output_path)
    return output_path
