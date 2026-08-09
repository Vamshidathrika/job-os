"""Global Ingestion Worker."""

from __future__ import annotations

import json
import structlog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg
    from jobos.config import Settings

from jobos.ingestion.poller import ATSPoller
from jobos.ingestion.normalizer import normalize_job
from jobos.ingestion.embedder import generate_embedding

logger = structlog.get_logger(__name__)


class GlobalIngestionWorker:
    """Worker to poll ATS and ingest jobs globally."""

    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        """Initialize the global ingestion worker."""
        self.pool = pool
        self.settings = settings
        self.poller = ATSPoller(settings=settings)

    async def run_cycle(self) -> None:
        """Fetch companies, poll each ATS, normalize, generate embeddings, and insert."""
        logger.info("starting_ingestion_cycle")
        
        async with self.pool.acquire() as conn:
            companies = await conn.fetch("SELECT company_id, company_domain, ats_type, ats_identifier FROM tenant_company_universe")
            
            for company in companies:
                company_id = company["company_id"]
                company_domain = company["company_domain"]
                ats_type = company["ats_type"]
                ats_identifier = company["ats_identifier"]
                
                raw_jobs = await self.poller.poll_company(
                    company_domain=company_domain,
                    ats_type=ats_type,
                    ats_identifier=ats_identifier,
                )
                
                for raw_job in raw_jobs:
                    try:
                        normalized = normalize_job(
                            ats_type=ats_type,
                            raw_job=raw_job,
                            company_id=str(company_id),
                            company_domain=company_domain,
                        )
                        
                        snippet = f"{normalized['title']} - {normalized['description'][:500]}"
                        embedding = await generate_embedding(text=snippet, settings=self.settings)
                        
                        await conn.execute(
                            """
                            INSERT INTO jobs (
                                company_id, external_id, title, location, country, 
                                description, raw_json, ats_type, embedding
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            ON CONFLICT (company_id, external_id) DO UPDATE SET
                                title = EXCLUDED.title,
                                location = EXCLUDED.location,
                                country = EXCLUDED.country,
                                description = EXCLUDED.description,
                                raw_json = EXCLUDED.raw_json,
                                ats_type = EXCLUDED.ats_type,
                                embedding = EXCLUDED.embedding
                            """,
                            normalized["company_id"],
                            normalized["external_id"],
                            normalized["title"],
                            normalized["location"],
                            normalized["country"],
                            normalized["description"],
                            json.dumps(normalized["raw_json"]),
                            normalized["ats_type"],
                            json.dumps(embedding)
                        )
                    except Exception as e:
                        logger.error("job_ingestion_failed", company_id=str(company_id), external_id=raw_job.get("external_id"), error=str(e))
                        
        logger.info("finished_ingestion_cycle")
