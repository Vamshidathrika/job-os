import pytest
from unittest.mock import AsyncMock

from jobos.workers.ingestion_worker import GlobalIngestionWorker
from jobos.db.models import Job

@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_ingestion_cycle(mocker):
    # Mock ATS poller
    mock_poller = mocker.patch("jobos.workers.ingestion_worker.ATSPoller.poll_greenhouse", new_callable=AsyncMock)
    mock_poller.return_value = [
        {
            "external_id": "gh-999",
            "title": "Backend Engineer",
            "location": "Remote, India",
            "description": "<p>Build scalable systems.</p>"
        }
    ]
    
    # Mock Embeddings if necessary, or DB inserts if it's a partial integration
    # Depending on architecture, we might just mock the embedding client
    mock_embed = mocker.patch("jobos.workers.ingestion_worker.generate_embeddings", new_callable=AsyncMock)
    mock_embed.return_value = [0.1] * 768
    
    # Mock DB insertion
    mock_db_insert = mocker.patch("jobos.workers.ingestion_worker.db_insert_job", new_callable=AsyncMock)
    
    worker = GlobalIngestionWorker()
    await worker.run_cycle(companies=["test_co"])
    
    # Verify poller called
    mock_poller.assert_called_once_with("test_co")
    
    # Verify embedding called
    mock_embed.assert_called()
    
    # Verify DB insert called with normalized fields
    mock_db_insert.assert_called_once()
    inserted_job = mock_db_insert.call_args[0][0]
    
    assert inserted_job["external_id"] == "gh-999"
    assert inserted_job["title"] == "Backend Engineer"
    assert "country" in inserted_job
    assert inserted_job["country"] == "IN"
    assert "embeddings" in inserted_job
    assert len(inserted_job["embeddings"]) == 768
