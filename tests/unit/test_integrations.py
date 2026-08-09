import pytest
from jobos.integrations.gmail import GmailClient

@pytest.fixture
def gmail_client() -> GmailClient:
    return GmailClient(tenant_id="tenant_123")

@pytest.mark.asyncio
async def test_parse_recruiter_reply_interested(gmail_client: GmailClient) -> None:
    """Test parsing an interested recruiter reply."""
    reply = "Thanks for your time. We are interested in moving forward to next steps."
    result = await gmail_client.parse_recruiter_reply(reply)
    
    assert result["intent"] == "interested"

@pytest.mark.asyncio
async def test_parse_recruiter_reply_rejected(gmail_client: GmailClient) -> None:
    """Test parsing a rejection reply."""
    reply = "Unfortunately, we have decided not to proceed with your application at this time."
    result = await gmail_client.parse_recruiter_reply(reply)
    
    assert result["intent"] == "rejected"
