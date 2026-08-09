"""Circuit breaker for runaway automation."""

from __future__ import annotations

from typing import Any
import structlog

logger = structlog.get_logger(__name__)

class CircuitBreaker:
    """Prevents runaway automation by tracking and limiting actions."""

    def __init__(self, tenant_id: str, max_daily_applies: int = 20, max_daily_emails: int = 10) -> None:
        """Initialize the CircuitBreaker.
        
        Args:
            tenant_id: The ID of the tenant.
            max_daily_applies: Maximum number of applications allowed per day.
            max_daily_emails: Maximum number of emails allowed per day.
        """
        self.tenant_id = tenant_id
        self.max_daily_applies = max_daily_applies
        self.max_daily_emails = max_daily_emails
        self.action_counts: dict[str, int] = {"applies": 0, "emails": 0}
        self._logger = logger.bind(tenant_id=tenant_id)

    def check(self, action_type: str) -> bool:
        """Check if a specific action is allowed.
        
        Args:
            action_type: The type of action (e.g., 'applies', 'emails').
            
        Returns:
            True if the action is allowed, False if the breaker is tripped.
        """
        count = self.action_counts.get(action_type, 0)
        limit = getattr(self, f"max_daily_{action_type}", float('inf'))
        is_allowed = count < limit
        
        if not is_allowed:
            self._logger.warning("Circuit breaker tripped", action_type=action_type, count=count, limit=limit)
        
        return is_allowed

    def record_action(self, action_type: str) -> None:
        """Record an action being taken.
        
        Args:
            action_type: The type of action taken.
        """
        if action_type in self.action_counts:
            self.action_counts[action_type] += 1
            self._logger.info("Recorded action", action_type=action_type, new_count=self.action_counts[action_type])

    def get_status(self) -> dict[str, Any]:
        """Get the current state of the circuit breaker.
        
        Returns:
            Dict containing the current state.
        """
        return {
            "action_counts": self.action_counts.copy(),
            "limits": {
                "applies": self.max_daily_applies,
                "emails": self.max_daily_emails
            }
        }
