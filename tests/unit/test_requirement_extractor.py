from unittest.mock import AsyncMock

import pytest

from jobos.ingestion.requirement_extractor import extract_hard_requirements


@pytest.mark.asyncio
async def test_extracts_requirements_from_description(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(
        content='{"hard_requirements": ["Python", "PostgreSQL", "Kubernetes"]}'
    ))]
    mocker.patch(
        "jobos.ingestion.requirement_extractor.acompletion",
        AsyncMock(return_value=mock_response),
    )
    settings = mocker.MagicMock()
    settings.llm.platform_groq_key = "fake-key"
    settings.llm.tailoring_model = "groq/llama-3.1-8b-instant"

    result = await extract_hard_requirements("We need 5+ years Python, PostgreSQL, and K8s experience.", settings)

    assert result == ["Python", "PostgreSQL", "Kubernetes"]


@pytest.mark.asyncio
async def test_returns_empty_list_on_malformed_llm_response(mocker):
    mock_response = mocker.MagicMock()
    mock_response.choices = [mocker.MagicMock(message=mocker.MagicMock(content="not json"))]
    mocker.patch(
        "jobos.ingestion.requirement_extractor.acompletion",
        AsyncMock(return_value=mock_response),
    )
    settings = mocker.MagicMock()
    settings.llm.platform_groq_key = "fake-key"
    settings.llm.tailoring_model = "groq/llama-3.1-8b-instant"

    result = await extract_hard_requirements("garbage in", settings)

    assert result == []
