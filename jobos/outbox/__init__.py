"""Outbound send path with compliance and rate guards."""

from jobos.outbox.sender import (
    SendingCapReachedError,
    SuppressedRecipientError,
    send_email_guarded,
)

__all__ = [
    "SendingCapReachedError",
    "SuppressedRecipientError",
    "send_email_guarded",
]
