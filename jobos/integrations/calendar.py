"""Google Calendar integration."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from jobos.composio_client import ComposioClient

logger = structlog.get_logger(__name__)

CREATE_EVENT_ACTION = "GOOGLECALENDAR_CREATE_EVENT"
FIND_FREE_SLOTS_ACTION = "GOOGLECALENDAR_FIND_FREE_SLOTS"
FIND_EVENT_ACTION = "GOOGLECALENDAR_FIND_EVENT"


class CalendarClient:
    """Client for interacting with Google Calendar."""

    def __init__(self, tenant_id: str, composio: ComposioClient | None = None) -> None:
        """Initialize the Calendar client for a specific tenant.

        Args:
            tenant_id: The ID of the tenant.
            composio: Injected Composio client; constructed per-tenant if omitted.
        """
        self.tenant_id = tenant_id
        self.composio = composio or ComposioClient(tenant_id=tenant_id)
        self._logger = logger.bind(tenant_id=tenant_id)

    async def create_event(
        self, title: str, start: datetime, end: datetime, description: str = ""
    ) -> dict[str, str]:
        """Create a new calendar event.

        Args:
            title: Event title.
            start: Start time.
            end: End time.
            description: Event description.

        Returns:
            Dict containing the created event_id.
        """
        self._logger.info("creating_calendar_event", title=title, start=start, end=end)

        data = await self.composio.execute(
            CREATE_EVENT_ACTION,
            {
                "summary": title,
                "description": description,
                "start_datetime": start.isoformat(),
                "event_duration_minutes": max(1, int((end - start).total_seconds() // 60)),
            },
        )
        event_id = str(data.get("id") or data.get("event_id") or "")
        self._logger.info("calendar_event_created", event_id=event_id)
        return {"event_id": event_id, "html_link": str(data.get("htmlLink") or "")}

    async def get_availability(
        self, date: datetime, duration_minutes: int = 60
    ) -> list[dict[str, Any]]:
        """Get available slots for a given date.

        Args:
            date: The date to check availability.
            duration_minutes: Required slot duration in minutes.

        Returns:
            List of available time slots.
        """
        self._logger.info("checking_availability", date=date, duration_minutes=duration_minutes)

        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        data = await self.composio.execute(
            FIND_FREE_SLOTS_ACTION,
            {
                "time_min": day_start.isoformat(),
                "time_max": (day_start + timedelta(days=1)).isoformat(),
            },
        )

        slots = self._extract_free_slots(data)
        # Only surface windows that can actually fit the requested meeting.
        usable = [s for s in slots if self._slot_minutes(s) >= duration_minutes]
        self._logger.info("availability_computed", total=len(slots), usable=len(usable))
        return usable

    async def block_prep_time(
        self, interview_event_id: str, prep_minutes: int = 60
    ) -> dict[str, str]:
        """Auto-block prep time before an interview.

        Args:
            interview_event_id: The ID of the interview event.
            prep_minutes: Minutes to block before the interview.

        Returns:
            Dict containing the prep event_id.
        """
        self._logger.info(
            "blocking_prep_time",
            interview_event_id=interview_event_id,
            prep_minutes=prep_minutes,
        )

        event = await self.composio.execute(
            FIND_EVENT_ACTION, {"event_id": interview_event_id}
        )
        interview_start = self._parse_event_start(event)
        if interview_start is None:
            raise ValueError(
                f"Could not determine start time for event {interview_event_id!r}; "
                "cannot place prep block"
            )

        prep_start = interview_start - timedelta(minutes=prep_minutes)
        return await self.create_event(
            title="Interview prep",
            start=prep_start,
            end=interview_start,
            description=f"Auto-blocked prep for event {interview_event_id}",
        )

    @staticmethod
    def _extract_free_slots(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Pull the free/busy slot list out of Composio's response shape."""
        calendars = data.get("calendars")
        if isinstance(calendars, dict):
            collected: list[dict[str, Any]] = []
            for calendar in calendars.values():
                if isinstance(calendar, dict) and isinstance(calendar.get("busy"), list):
                    collected.extend(calendar["busy"])
            return collected
        for key in ("free_slots", "slots", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return []

    @staticmethod
    def _slot_minutes(slot: dict[str, Any]) -> float:
        """Duration of a {start,end} slot in minutes; 0 if unparseable."""
        start_raw = slot.get("start") or slot.get("start_time")
        end_raw = slot.get("end") or slot.get("end_time")
        if not start_raw or not end_raw:
            return 0.0
        try:
            start = datetime.fromisoformat(str(start_raw).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        return (end - start).total_seconds() / 60

    @staticmethod
    def _parse_event_start(event: dict[str, Any]) -> datetime | None:
        """Extract an event's start datetime from Composio's response shape."""
        start = event.get("start")
        raw = start.get("dateTime") if isinstance(start, dict) else start
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
