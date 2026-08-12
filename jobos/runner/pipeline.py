"""Sequences the pipeline stages. Each stage is idempotent and independently runnable."""

from __future__ import annotations

from typing import Any

import structlog

from jobos.action_queue.executor import ActionExecutor
from jobos.action_queue.queue import ActionQueue
from jobos.db.pool import global_conn, tenant_conn
from jobos.ingestion.seed_companies import seed_companies
from jobos.integrations.drive import DriveClient
from jobos.matcher.pipeline import run_matching
from jobos.runner.handlers import build_handlers
from jobos.runner.warm_paths import start_races_for_tier_1
from jobos.tailorer.generator import generate_tailored_resume
from jobos.warm_path.race import WarmPathRace, find_expired_races
from jobos.workers.global_ingestion import GlobalIngestionWorker

logger = structlog.get_logger(__name__)


async def stage_seed(pool: Any, seed_path: str | None = None) -> dict[str, int]:
    """Upsert the company universe."""
    async with global_conn(pool) as conn:
        return await seed_companies(conn, seed_path)


async def stage_ingest(pool: Any, settings: Any) -> dict[str, int]:
    """Poll every seeded board and store the jobs."""
    worker = GlobalIngestionWorker(pool=pool, settings=settings)
    return await worker.run_cycle()


async def stage_match(pool: Any, user_id: str) -> dict[str, int]:
    """Score ingested jobs against the Career Graph."""
    async with tenant_conn(pool, user_id) as conn:
        return await run_matching(conn, user_id)


async def stage_race(pool: Any, user_id: str, settings: Any) -> dict[str, int]:
    """Start races for Tier-1 matches and resolve any that have expired."""
    async with tenant_conn(pool, user_id) as conn:
        started = await start_races_for_tier_1(conn, user_id, settings=settings)

        resolved = 0
        for expired in await find_expired_races(conn):
            race = WarmPathRace(conn=conn, job_id=expired["job_id"], tenant_id=user_id)
            await race.resolve_race()
            resolved += 1

    return {**started, "resolved": resolved}


async def stage_work(pool: Any, user_id: str) -> dict[str, int]:
    """Execute due Band A actions."""
    async with tenant_conn(pool, user_id) as conn:
        queue = ActionQueue(conn=conn, tenant_id=user_id)
        executor = ActionExecutor(queue, handlers=build_handlers(conn, user_id))
        return await executor.process_band_a()


class NoJobFoundError(LookupError):
    """Raised when the given job_id doesn't exist."""


class NoVerifiedBulletsError(ValueError):
    """Raised when the tenant has no verified Career Graph bullets to tailor from."""


async def stage_upload_resume(
    pool: Any, user_id: str, job_id: str, settings: Any
) -> dict[str, str]:
    """Tailor a resume for one job and save it to the tenant's Google Drive.

    Unlike the other stages, this operates on a single job rather than the
    whole tenant — it's invoked per-application, not per pipeline run, so it
    is deliberately not part of run_full_pipeline's automatic sequence.

    Args:
        pool: The connection pool.
        user_id: The tenant this resume is for.
        job_id: The job to tailor against.
        settings: Application settings, forwarded to the tailorer.

    Returns:
        dict with file_id and web_view_link from Drive, plus used_bullet_ids.

    Raises:
        NoJobFoundError: job_id doesn't exist.
        NoVerifiedBulletsError: nothing verified to tailor from.
        ComposioActionError: the Drive upload itself failed.
    """
    async with tenant_conn(pool, user_id) as conn:
        job = await conn.fetchrow(
            "SELECT title, description FROM jobs WHERE id = $1::uuid", job_id
        )
        if job is None:
            raise NoJobFoundError(f"No job {job_id!r}")

        bullets = [
            dict(row)
            for row in await conn.fetch(
                "SELECT id, bullet_text, role, company, metric FROM cg_bullets "
                "WHERE user_id = $1::uuid AND verification_status = 'verified'",
                user_id,
            )
        ]
        if not bullets:
            raise NoVerifiedBulletsError(
                "No verified Career Graph bullets — nothing safe to tailor from"
            )

        tailored = await generate_tailored_resume(
            job_description=job["description"] or job["title"] or "",
            verified_bullets=bullets,
            settings=settings,
        )
        if not tailored["tailored_text"]:
            raise NoVerifiedBulletsError(
                "Tailoring produced no usable text (see logs for the underlying cause)"
            )

        drive = DriveClient(tenant_id=user_id)
        folder = await drive.ensure_folder()
        uploaded = await drive.upload_resume(
            tenant_id=user_id,
            filename=f"resume-{job['title'] or job_id}.txt",
            text_content=tailored["tailored_text"],
            folder_id=folder["folder_id"],
        )

    return {**uploaded, "used_bullet_ids": tailored["used_bullet_ids"]}


async def run_full_pipeline(
    pool: Any, user_id: str, settings: Any, seed_path: str | None = None
) -> dict[str, dict]:
    """Run every stage in order, returning each stage's counts."""
    logger.info("pipeline_start", user_id=user_id)

    results = {
        "seed": await stage_seed(pool, seed_path),
        "ingest": await stage_ingest(pool, settings),
        "match": await stage_match(pool, user_id),
        "race": await stage_race(pool, user_id, settings),
        "work": await stage_work(pool, user_id),
    }

    logger.info("pipeline_complete", **{k: str(v) for k, v in results.items()})
    return results
