"""Unit tests for the allowlist-based credential scrubber."""

import pytest

from jobos.vault.redaction import scrub


@pytest.mark.parametrize("credential,description", [
    ("sk-or-v1-abcdef1234567890abcdef1234567890", "OpenRouter key"),
    ("gsk_abcdef1234567890abcdef", "Groq key"),
    ("sk-proj-abcdef1234567890abcdef1234567890", "OpenAI project key"),
    ("sk-abcdef1234567890abcdef1234567890abcdef1234", "OpenAI generic key"),
    ("Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkw", "Bearer JWT"),
    ("ya29.a0AfB_byCdef1234567890abcdef", "Google OAuth token"),
    ("AKIAIOSFODNN7EXAMPLE", "AWS access key"),
    ("AQVabcdef1234567890abcdef1234567890", "LinkedIn token"),
    ("nvapi-abcdef1234567890abcdef1234567890", "NVIDIA NIM key"),
    ("comp-abcdef1234567890abcdef1234567890", "Composio key"),
    ("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "64-char hex secret"),
    ("eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IjEyMzQ1Njc4OTAifQ", "Base64 JWT payload"),
])
def test_scrubber_redacts_credential_pattern(credential: str, description: str) -> None:
    """Each known credential pattern must be scrubbed to [REDACTED]."""
    text = f"Error connecting with key: {credential} to the API"
    result = scrub(text)
    assert credential not in result, f"Failed to redact {description}: {credential}"
    assert "[REDACTED]" in result


def test_scrubber_handles_dict() -> None:
    """Scrubber must recursively walk dicts."""
    data = {
        "module": "referral",
        "api_key": "sk-or-v1-leaked1234567890abcdef1234567890",
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
    }
    result = scrub(data)
    assert result["module"] == "referral"
    assert "sk-or-v1" not in str(result["api_key"])
    assert result["user_id"] == "550e8400-e29b-41d4-a716-446655440000"


def test_scrubber_handles_nested_structures() -> None:
    """Deeply nested dicts and lists must be fully scrubbed."""
    data = {
        "error": {
            "details": [
                {"key": "gsk_leaked_key_abcdef1234567890"},
                {"nested": {"deep": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload"}},
            ]
        }
    }
    result = scrub(data)
    flat = str(result)
    assert "gsk_" not in flat
    assert "Bearer eyJ" not in flat
    assert "[REDACTED]" in flat


def test_scrubber_handles_list() -> None:
    """Lists of strings must each be individually scrubbed."""
    data = ["safe text", "key is sk-or-v1-test1234567890abcdef1234567890", "more safe"]
    result = scrub(data)
    assert result[0] == "safe text"
    assert "sk-or-v1" not in result[1]
    assert result[2] == "more safe"


def test_scrubber_preserves_safe_values() -> None:
    """Non-credential strings must pass through unchanged."""
    safe_values = [
        "This is a normal log message",
        "user_id=550e8400-e29b-41d4-a716-446655440000",
        "module=referral action=score_referrer",
        42,
        3.14,
        True,
        None,
    ]
    for val in safe_values:
        assert scrub(val) == val


def test_scrubber_handles_none_and_empty() -> None:
    """Edge cases: None, empty string, empty dict, empty list."""
    assert scrub(None) is None
    assert scrub("") == ""
    assert scrub({}) == {}
    assert scrub([]) == []


def test_planted_key_in_error_traceback() -> None:
    """Simulate an error payload containing a real-looking API key in a traceback string."""
    traceback_str = (
        'Traceback (most recent call last):\n'
        '  File "jobos/composio_client/gmail.py", line 42, in send_email\n'
        '    response = await client.post(url, headers={"Authorization": '
        '"Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6InRlc3QifQ.payload.signature"})\n'
        'httpx.HTTPStatusError: 401 Unauthorized'
    )
    result = scrub(traceback_str)
    assert "eyJhbGciOiJ" not in result
    assert "[REDACTED]" in result
    assert "401 Unauthorized" in result  # preserve the useful error info
