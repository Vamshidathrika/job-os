"""Global Ingestion Worker."""

from __future__ import annotations

import json
import structlog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg
    from jobos.config import Settings

from jobos.db.models import EMBEDDING_DIM
from jobos.ingestion.poller import ATSPoller
from jobos.ingestion.normalizer import normalize_job
from jobos.ingestion.embedder import generate_embedding
from jobos.ingestion.requirement_extractor import extract_hard_requirements

logger = structlog.get_logger(__name__)


class GlobalIngestionWorker:
    """Worker to poll ATS and ingest jobs globally."""

    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        """Initialize the global ingestion worker."""
        self.pool = pool
        self.settings = settings
        self.poller = ATSPoller(settings=settings)

    async def run_cycle(self) -> dict[str, int]:
        """Fetch companies, poll each ATS, normalize, generate embeddings, and insert.

        Returns:
            Counts of jobs seen/ingested/failed for this cycle, so callers (and
            the circuit breakers) can tell a healthy empty poll apart from a
            cycle where every single insert blew up.
        """
        logger.info("starting_ingestion_cycle")
        seen = ingested = failed = 0

        async with self.pool.acquire() as conn:
            # Read the global company universe, NOT tenant_company_universe:
            # this worker runs with no tenant context, and
            # tenant_company_universe is RLS-protected, so it would return
            # zero rows here. That table is the per-tenant target list used
            # downstream by the matcher.
            companies = await conn.fetch(
                "SELECT id, domain, ats_type, ats_identifier FROM companies "
                "WHERE ats_type IS NOT NULL AND ats_identifier IS NOT NULL"
            )

            for company in companies:
                company_id = company["id"]
                company_domain = company["domain"]
                ats_type = company["ats_type"]
                ats_identifier = company["ats_identifier"]

                raw_jobs = await self.poller.poll_company(
                    company_domain=company_domain,
                    ats_type=ats_type,
                    ats_identifier=ats_identifier,
                )

                for raw_job in raw_jobs:
                    seen += 1
                    try:
                        normalized = normalize_job(
                            ats_type=ats_type,
                            raw_job=raw_job,
                            company_id=str(company_id),
                            company_domain=company_domain,
                        )

                        snippet = f"{normalized['title']} - {normalized['description'][:500]}"
                        embedding = await generate_embedding(text=snippet, settings=self.settings)
                        if len(embedding) != EMBEDDING_DIM:
                            raise ValueError(
                                f"embedding width {len(embedding)} != column width {EMBEDDING_DIM}"
                            )

                        # jobs.id defaults to gen_random_uuid(); jsonb and vector
                        # params must be cast explicitly since both are sent as text.
                        job_id = await conn.fetchval(
                            """
                            INSERT INTO jobs (
                                company_id, external_id, title, location, country,
                                description, raw_json, ats_type, embedding
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9::vector)
                            ON CONFLICT (company_id, external_id) DO UPDATE SET
                                title = EXCLUDED.title,
                                location = EXCLUDED.location,
                                country = EXCLUDED.country,
                                description = EXCLUDED.description,
                                raw_json = EXCLUDED.raw_json,
                                ats_type = EXCLUDED.ats_type,
                                embedding = EXCLUDED.embedding
                            RETURNING id
                            """,
                            company_id,
                            normalized["external_id"],
                            normalized["title"],
                            normalized["location"],
                            normalized["country"],
                            normalized["description"],
                            json.dumps(normalized["raw_json"]),
                            normalized["ats_type"],
                            json.dumps(embedding),
                        )
                        ingested += 1

                        # Best-effort: a failed extraction must not undo the
                        # job insert above (ingested is already counted), so
                        # it gets its own try/except rather than sharing the
                        # outer one.
                        #
                        # run_cycle is re-run repeatedly (every poll
                        # re-upserts every posting via ON CONFLICT DO
                        # UPDATE), so extraction must only happen once per
                        # job — otherwise a stable, unchanged job re-triggers
                        # a real LLM call on every single ingestion cycle,
                        # forever.
                        try:
                            already_extracted = await conn.fetchval(
                                "SELECT 1 FROM job_requirements "
                                "WHERE job_id = $1 AND hard_reqs IS NOT NULL",
                                job_id,
                            )
                            if not already_extracted:
                                hard_reqs = await extract_hard_requirements(
                                    normalized["description"], self.settings
                                )
                                if hard_reqs:
                                    await conn.execute(
                                        "INSERT INTO job_requirements (job_id, hard_reqs) "
                                        "VALUES ($1, $2::jsonb) "
                                        "ON CONFLICT (job_id) DO UPDATE SET hard_reqs = EXCLUDED.hard_reqs",
                                        job_id,
                                        json.dumps(hard_reqs),
                                    )
                        except Exception as e:
                            logger.warning(
                                "requirement_extraction_ingestion_failed",
                                job_id=str(job_id),
                                error=str(e),
                            )
                    except Exception as e:
                        # One malformed posting must not kill the cycle, but a
                        # swallowed error here previously hid a 100% failure
                        # rate — hence the counters and the summary below.
                        failed += 1
                        logger.error(
                            "job_ingestion_failed",
                            company_id=str(company_id),
                            external_id=raw_job.get("external_id"),
                            error=str(e),
                        )

        if seen and not ingested:
            logger.error("ingestion_cycle_total_failure", seen=seen, failed=failed)
        logger.info("finished_ingestion_cycle", seen=seen, ingested=ingested, failed=failed)
        return {"seen": seen, "ingested": ingested, "failed": failed}
