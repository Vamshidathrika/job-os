"""Comp field defensive policy (v2 §5.2)."""

from __future__ import annotations

import structlog
from typing import Any

logger = structlog.get_logger(__name__)


def handle_comp_field(field_type: str, field_value: str | None, predicted_band: dict[str, Any]) -> dict[str, str]:
    """
    Handle compensation fields based on defensive policy rules.
    """
    logger.info("handling_comp_field", field_type=field_type)
    
    if field_type == "text":
        return {
            "action": "deflect", 
            "value": "Open to discussion based on total compensation and market standards."
        }
    
    elif field_type == "numeric_required":
        p75_val = str(predicted_band.get("p75", 0.0))
        return {
            "action": "fill", 
            "value": p75_val
        }
        
    elif field_type == "current_ctc":
        return {
            "action": "escalate_band_c", 
            "reason": "Current CTC is a mandatory human escalation"
        }
        
    # Default fallback
    return {
        "action": "skip", 
        "reason": f"Unknown field type: {field_type}"
    }
