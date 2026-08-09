"""ATS form field mapper."""
from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)

def map_fields(form_fields: list[dict[str, str]], user_data: dict[str, Any]) -> dict[str, str]:
    """
    Maps detected form fields to user data using fuzzy matching.
    
    Args:
        form_fields: List of dictionaries describing form fields.
        user_data: User's profile data.
        
    Returns:
        Mapping of field_id to its corresponding user data value.
    """
    logger.info("mapping_fields", num_fields=len(form_fields))
    mapped = {}
    for field in form_fields:
        field_id = field.get("id")
        if not field_id:
            continue
            
        if field_id in user_data:
            mapped[field_id] = str(user_data[field_id])
            
    return mapped
