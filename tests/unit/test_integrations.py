"""Unit tests for the Composio-backed Gmail and Calendar integrations.

A fake ComposioClient stands in for the SDK — there is no API key in CI — but
the request shaping, response parsing and failure propagation under test are
the real implementations.
"""

from datetime import datetime, timedelta, timezone

import pytest

from jobos.composio_client import ComposioActionError, ComposioClient, ComposioNotConfiguredError
from jobos.config import Settings
from jobos.integrations.calendar import CalendarClient
from jobos.integrations.gmail import GmailClient


class FakeComposio:
    """Records executed actions and replays canned responses."""

    def __init__(self, responses=None, error: Exception | None = None):
        self.responses = responses or {}
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, action: str, params: dict) -> dict:
        self.calls.append((action, params))
        if self.error:
            raise self.error
        return self.responses.get(action, {})


async def test_send_email_shapes_request_and_returns_real_id():
    fake = FakeComposio({"GMAIL_SEND_EMAIL": {"id": "18f2a", "threadId": "t-9"}})
    client = GmailClient(tenant_id="t1", composio=fake)

    result = await client.send_email(
        to="dev@example.com", subject="Hello", body="Body text", reply_to="me@example.com"
    )

    action, params = fake.calls[0]
    assert action == "GMAIL_SEND_EMAIL"
    assert params["recipient_email"] == "dev@example.com"
    assert params["subject"] == "Hello"
    assert params["extra_headers"] == {"Reply-To": "me@example.com"}

    assert result["message_id"] == "18f2a"
    assert result["message_id"] != "mock_msg_id"


async def test_send_email_propagates_failure_instead_of_faking_success():
    """A failed send must raise — never report status 'sent'."""
    fake = FakeComposio(error=ComposioActionError("gmail rejected the message"))
    client = GmailClient(tenant_id="t1", composio=fake)

    with pytest.raises(ComposioActionError):
        await client.send_email(to="dev@example.com", subject="s", body="b")


async def test_watch_inbox_returns_messages():
    fake = FakeComposio({"GMAIL_FETCH_EMAILS": {"messages": [{"id": "m1"}, {"id": "m2"}]}})
    client = GmailClient(tenant_id="t1", composio=fake)

    messages = await client.watch_inbox(labels=["INBOX"])

    assert [m["id"] for m in messages] == ["m1", "m2"]
    assert fake.calls[0][1]["label_ids"] == ["INBOX"]


async def test_create_event_sends_duration_and_returns_real_id():
    fake = FakeComposio({"GOOGLECALENDAR_CREATE_EVENT": {"id": "evt-77"}})
    client = CalendarClient(tenant_id="t1", composio=fake)
    start = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)

    result = await client.create_event(
        title="Interview", start=start, end=start + timedelta(minutes=45)
    )

    action, params = fake.calls[0]
    assert action == "GOOGLECALENDAR_CREATE_EVENT"
    assert params["event_duration_minutes"] == 45
    assert result["event_id"] == "evt-77"
    assert result["event_id"] != "mock_event_id"


async def test_get_availability_filters_slots_shorter_than_requested():
    start = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    fake = FakeComposio(
        {
            "GOOGLECALENDAR_FIND_FREE_SLOTS": {
                "free_slots": [
                    # 30 minutes — too short for a 60 minute meeting.
                    {"start": start.isoformat(), "end": (start + timedelta(minutes=30)).isoformat()},
                    # 90 minutes — fits.
                    {
                        "start": (start + timedelta(hours=2)).isoformat(),
                        "end": (start + timedelta(hours=3, minutes=30)).isoformat(),
                    },
                ]
            }
        }
    )
    client = CalendarClient(tenant_id="t1", composio=fake)

    slots = await client.get_availability(date=start, duration_minutes=60)

    assert len(slots) == 1
    assert slots[0]["start"] == (start + timedelta(hours=2)).isoformat()


async def test_block_prep_time_places_block_before_the_interview():
    interview_start = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    fake = FakeComposio(
        {
            "GOOGLECALENDAR_FIND_EVENT": {"start": {"dateTime": interview_start.isoformat()}},
            "GOOGLECALENDAR_CREATE_EVENT": {"id": "prep-1"},
        }
    )
    client = CalendarClient(tenant_id="t1", composio=fake)

    result = await client.block_prep_time("evt-1", prep_minutes=30)

    created = dict(fake.calls[-1][1])
    assert created["start_datetime"] == (interview_start - timedelta(minutes=30)).isoformat()
    assert created["event_duration_minutes"] == 30
    assert result["event_id"] == "prep-1"


async def test_block_prep_time_refuses_when_start_unknown():
    """Without a real interview time we must not invent a prep slot."""
    fake = FakeComposio({"GOOGLECALENDAR_FIND_EVENT": {}, "GOOGLECALENDAR_CREATE_EVENT": {"id": "x"}})
    client = CalendarClient(tenant_id="t1", composio=fake)

    with pytest.raises(ValueError):
        await client.block_prep_time("evt-missing")


async def test_composio_client_requires_api_key():
    settings = Settings()
    settings.composio.api_key = ""
    client = ComposioClient(tenant_id="t1", settings=settings)

    assert client.is_configured is False
    with pytest.raises(ComposioNotConfiguredError):
        await client.execute("GMAIL_SEND_EMAIL", {})


async def test_composio_client_raises_on_unsuccessful_response(mocker):
    settings = Settings()
    settings.composio.api_key = "test-key"
    client = ComposioClient(tenant_id="t1", settings=settings)

    fake_toolset = mocker.Mock()
    fake_toolset.execute_action.return_value = {
        "successful": False,
        "error": "invalid connected account",
    }
    client._toolset = fake_toolset

    with pytest.raises(ComposioActionError, match="invalid connected account"):
        await client.execute("GMAIL_SEND_EMAIL", {"recipient_email": "a@b.c"})
