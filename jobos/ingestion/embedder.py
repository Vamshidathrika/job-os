"""Embedder for jobs."""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import structlog
from litellm import aembedding

if TYPE_CHECKING:
    from jobos.config import Settings

logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _local_model(model_name: str) -> Any:
    """Load the ONNX embedding model once per process.

    The first call downloads roughly 50MB to the fastembed cache; subsequent
    runs are offline.
    """
    from fastembed import TextEmbedding

    logger.info("loading_local_embedding_model", model=model_name)
    return TextEmbedding(model_name=model_name)


async def generate_embedding(text: str, settings: Settings | None = None) -> list[float]:
    """Generate an embedding for job title + description snippet.

    Runs a local ONNX model by default so matching needs no credential. Set
    LLMSettings.embedding_local to False to route through litellm instead.

    Raises:
        ValueError: if the text is empty — an all-zero vector would silently
            match everything.
    """
    if settings is None:
        from jobos.config import settings as default_settings

        settings = default_settings

    if not text.strip():
        raise ValueError("Cannot embed empty text")

    model = settings.llm.embedding_model

    if settings.llm.embedding_local:
        def _embed() -> list[float]:
            vectors = list(_local_model(model).embed([text]))
            return [float(v) for v in vectors[0]]

        # fastembed is synchronous CPU work; keep it off the event loop.
        return await asyncio.to_thread(_embed)

    try:
        response = await aembedding(model=model, input=[text])
        return [float(v) for v in response["data"][0]["embedding"]]
    except Exception as e:
        logger.error("embedding_generation_failed", error=str(e), model=model)
        raise
