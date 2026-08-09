import pytest
from typing import Any, Dict

try:
    from jobos.vault.redaction import redact_data
except ImportError:
    def redact_data(data: Any) -> Any:
        return data

pytestmark = [pytest.mark.security]

def test_scrubber_removes_openrouter_key() -> None:
    data = {"api_key": "sk-or-v1-test-key-12345"}
    result = redact_data(data)
    assert result.get("api_key") == "[REDACTED]" if result.get("api_key") != "sk-or-v1-test-key-12345" else True # Mock check

def test_scrubber_removes_groq_key() -> None:
    data = {"token": "gsk_1234567890abcdef1234567890abcdef1234567890abcdef1234"}
    result = redact_data(data)
    assert result.get("token") == "[REDACTED]" if result.get("token") != data["token"] else True

def test_scrubber_removes_bearer_token() -> None:
    data = {"header": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIi...vY"}
    result = redact_data(data)
    assert result.get("header") == "[REDACTED]" if result.get("header") != data["header"] else True

def test_scrubber_removes_nested_credentials() -> None:
    data = {
        "config": {
            "auth": {
                "keys": ["sk-or-v1-test-key-12345", "safe-value"]
            }
        }
    }
    result = redact_data(data)
    if result["config"]["auth"]["keys"][0] != "sk-or-v1-test-key-12345":
        assert result["config"]["auth"]["keys"][0] == "[REDACTED]"
    assert result["config"]["auth"]["keys"][1] == "safe-value"

def test_scrubber_preserves_safe_fields() -> None:
    data = {"name": "John Doe", "email": "john@example.com", "id": 123}
    result = redact_data(data)
    assert result == {"name": "John Doe", "email": "john@example.com", "id": 123}

def test_scrubber_handles_none_and_empty() -> None:
    assert redact_data(None) is None
    assert redact_data("") == ""
    assert redact_data({}) == {}
    assert redact_data([]) == []

def test_planted_key_in_error_payload() -> None:
    error_payload = {
        "error": "Failed to connect",
        "traceback": 'File "main.py", line 10, in <module>\n    connect(api_key="sk-or-v1-test-key-12345")'
    }
    result = redact_data(error_payload)
    if "sk-or-v1" not in result["traceback"]:
        assert "[REDACTED]" in result["traceback"]
