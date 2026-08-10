"""Gmail integration via Composio."""

from __future__ import annotations

from typing import Any

import structlog

from jobos.composio_client import ComposioClient

logger = structlog.get_logger(__name__)

SEND_EMAIL_ACTION = "GMAIL_SEND_EMAIL"
FETCH_EMAILS_ACTION = "GMAIL_FETCH_EMAILS"


class GmailClient:
    """Client for interacting with Gmail via Composio."""

    def __init__(self, tenant_id: str, composio: ComposioClient | None = None) -> None:
        """Initialize the Gmail client for a specific tenant.

        Args:
            tenant_id: The ID of the tenant.
            composio: Injected Composio client; constructed per-tenant if omitted.
        """
        self.tenant_id = tenant_id
        self.composio = composio or ComposioClient(tenant_id=tenant_id)
        self._logger = logger.bind(tenant_id=tenant_id)

    async def send_email(
        self, to: str, subject: str, body: str, reply_to: str | None = None
    ) -> dict[str, str]:
        """Send an email.

        Args:
            to: Recipient email address.
            subject: Email subject.
            body: Email body text.
            reply_to: Optional reply-to address.

        Returns:
            dict containing message_id and status.

        Raises:
            ComposioActionError: if the send failed. Never returns a success
                shape for an email that was not actually accepted by Gmail.
        """
        self._logger.info("sending_email", to=to, subject=subject)

        params: dict[str, Any] = {
            "recipient_email": to,
            "subject": subject,
            "body": body,
            "is_html": False,
        }
        if reply_to:
            params["extra_headers"] = {"Reply-To": reply_to}

        data = await self.composio.execute(SEND_EMAIL_ACTION, params)
        message_id = str(data.get("id") or data.get("message_id") or "")
        self._logger.info("email_sent", to=to, message_id=message_id)
        return {"message_id": message_id, "status": "sent", "thread_id": str(data.get("threadId") or "")}

    async def watch_inbox(self, labels: list[str], max_results: int = 25) -> list[dict[str, Any]]:
        """Fetch recent emails matching labels.

        Args:
            labels: List of Gmail labels to watch.
            max_results: Cap on messages returned per call.

        Returns:
            List of matching emails.
        """
        self._logger.info("watching_inbox", labels=labels)

        data = await self.composio.execute(
            FETCH_EMAILS_ACTION,
            {"label_ids": labels, "max_results": max_results},
        )
        messages = data.get("messages") or data.get("data") or []
        if not isinstance(messages, list):
            self._logger.warning("unexpected_inbox_payload", payload_type=type(messages).__name__)
            return []
        self._logger.info("inbox_fetched", count=len(messages))
        return messages

    async def parse_recruiter_reply(self, email_body: str) -> dict[str, Any]:
        """Extract intent from recruiter reply.

        Args:
            email_body: The content of the recruiter's email.

        Returns:
            Dict containing parsed intent (e.g., interested, rejected, scheduling).
        """
        self._logger.info("parsing_recruiter_reply")
        lower_body = email_body.lower()
        if "reject" in lower_body or "unfortunately" in lower_body:
            return {"intent": "rejected", "details": {}}
        elif "interest" in lower_body or "next steps" in lower_body:
            return {"intent": "interested", "details": {}}
        return {"intent": "scheduling", "details": {}}
