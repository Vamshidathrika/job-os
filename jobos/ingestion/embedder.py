"""Embedder for jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING
import structlog
from litellm import aembedding

if TYPE_CHECKING:
    from jobos.config import Settings

logger = structlog.get_logger(__name__)


async def generate_embedding(text: str, settings: Settings | None = None) -> list[float]:
    """Generate 1536-dim embedding for job title + description snippet using LiteLLM."""
    if settings is None:
        from jobos.config import settings as default_settings
        settings = default_settings

    model = settings.llm.embedding_model
    try:
        response = await aembedding(model=model, input=[text])
        embedding = response["data"][0]["embedding"]
        return embedding
    except Exception as e:
        logger.error("embedding_generation_failed", error=str(e), model=model)
        raise
