"""Tests for local embedding generation."""

import pytest

from jobos.db.models import EMBEDDING_DIM
from jobos.ingestion.embedder import generate_embedding


def test_embedding_dim_matches_local_model():
    assert EMBEDDING_DIM == 384


@pytest.mark.asyncio
async def test_embedding_has_the_column_width():
    vector = await generate_embedding("Backend engineer with Redis experience")

    assert len(vector) == EMBEDDING_DIM
    assert all(isinstance(v, float) for v in vector)


@pytest.mark.asyncio
async def test_similar_text_scores_higher_than_unrelated():
    """A real model must rank a paraphrase above an unrelated sentence."""
    from jobos.matcher.scorer import compute_similarity

    anchor = await generate_embedding("backend engineer building caching layers")
    near = await generate_embedding("server-side developer working on caches")
    far = await generate_embedding("pastry chef specialising in croissants")

    assert compute_similarity(anchor, near) > compute_similarity(anchor, far)


@pytest.mark.asyncio
async def test_empty_text_is_rejected():
    with pytest.raises(ValueError):
        await generate_embedding("   ")
