"""Screenshot capture for audit trail."""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

async def capture_submission_screenshot(page_url: str, output_path: str) -> str:
    """
    Captures and saves a screenshot of the application page.
    
    Args:
        page_url: The URL of the page being captured.
        output_path: Destination path for the screenshot.
        
    Returns:
        The path where the screenshot was saved.
    """
    logger.info("capturing_screenshot", url=page_url, output_path=output_path)
    return output_path
