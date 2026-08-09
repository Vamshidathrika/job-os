"""Async HTTP poller for ATS."""

from __future__ import annotations

import httpx
import structlog
import asyncio
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from jobos.config import Settings

logger = structlog.get_logger(__name__)


class ATSPoller:
    """Async HTTP poller with retries and pooling."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the poller."""
        self.settings = settings
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )

    async def _fetch_with_retry(self, url: str) -> dict[str, Any] | list[Any]:
        """Fetch URL with exponential backoff on 429/50x."""
        retries = 3
        for attempt in range(retries):
            try:
                response = await self.client.get(url)
                if response.status_code in (429, 500, 502, 503, 504):
                    logger.warning("http_retry", status_code=response.status_code, url=url, attempt=attempt)
                    await asyncio.sleep(2 ** attempt)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error("http_request_failed", url=url, error=str(e), attempt=attempt)
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        return {}

    async def poll_company(self, company_domain: str, ats_type: str, ats_identifier: str) -> list[dict[str, Any]]:
        """Poll the ATS for a specific company."""
        from jobos.ingestion.ats_parsers.greenhouse import parse_greenhouse_jobs
        from jobos.ingestion.ats_parsers.lever import parse_lever_jobs
        from jobos.ingestion.ats_parsers.ashby import parse_ashby_jobs
        from jobos.ingestion.ats_parsers.workday import parse_workday_jobs

        logger.info("polling_company", company_domain=company_domain, ats_type=ats_type)

        jobs = []
        try:
            if ats_type == "greenhouse":
                url = f"https://boards-api.greenhouse.io/v1/boards/{ats_identifier}/jobs?content=true"
                data = await self._fetch_with_retry(url)
                if isinstance(data, dict):
                    jobs = parse_greenhouse_jobs(data)
            elif ats_type == "lever":
                url = f"https://api.lever.co/v0/postings/{ats_identifier}?mode=json"
                data = await self._fetch_with_retry(url)
                if isinstance(data, list):
                    jobs = parse_lever_jobs(data)
            elif ats_type == "ashby":
                url = f"https://api.ashbyhq.com/posting-api/job-board/{ats_identifier}"
                data = await self._fetch_with_retry(url)
                if isinstance(data, dict):
                    jobs = parse_ashby_jobs(data)
            elif ats_type == "workday":
                url = f"https://{ats_identifier}/api/jobs"
                data = await self._fetch_with_retry(url)
                if isinstance(data, dict) or isinstance(data, list):
                    jobs = parse_workday_jobs(data) # type: ignore
            else:
                logger.warning("unknown_ats_type", ats_type=ats_type)
        except Exception as e:
            logger.error("polling_failed", company_domain=company_domain, ats_type=ats_type, error=str(e))
            
        return jobs
