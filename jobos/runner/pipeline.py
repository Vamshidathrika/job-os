"""Sequences the pipeline stages. Each stage is idempotent and independently runnable."""

from __future__ import annotations

from typing import Any

import structlog

from jobos.action_queue.executor import ActionExecutor
from jobos.action_queue.queue import ActionQueue
from jobos.db.pool import global_conn, tenant_conn
from jobos.ingestion.seed_companies import seed_companies
from jobos.matcher.pipeline import run_matching
from jobos.runner.handlers import build_handlers
from jobos.runner.warm_paths import start_races_for_tier_1
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
