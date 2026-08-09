"""Integrations module for external services like Gmail and Google Calendar."""

from __future__ import annotations

from .gmail import GmailClient
from .calendar import CalendarClient

__all__ = ["GmailClient", "CalendarClient"]
