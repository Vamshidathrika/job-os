"""JOBOS command line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import structlog

from jobos.config import settings
from jobos.db.pool import create_pool, tenant_conn
from jobos.runner.pipeline import (
    run_full_pipeline,
    stage_ingest,
    stage_match,
    stage_race,
    stage_seed,
    stage_work,
)

logger = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobos", description="Autonomous warm-path job search")
    parser.add_argument("--user-id", required=True, help="Tenant/user UUID to act as")
    sub = parser.add_subparsers(dest="command", required=True)

    importer = sub.add_parser("import", help="Import a LinkedIn export and/or resume")
    importer.add_argument("--linkedin-zip")
    importer.add_argument("--resume")

    seed = sub.add_parser("seed", help="Seed the company universe")
    seed.add_argument("--file")

    sub.add_parser("ingest", help="Poll job boards")
    sub.add_parser("match", help="Score jobs against your profile")
    sub.add_parser("race", help="Start and resolve warm-path races")
    sub.add_parser("work", help="Execute due queued actions")

    run = sub.add_parser("run", help="Run the whole pipeline")
    run.add_argument("--seed-file")

    return parser


async def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    pool = await create_pool(settings)
    try:
        if args.command == "import":
            from jobos.onboarding.linkedin_import import import_profile

            async with tenant_conn(pool, args.user_id) as conn:
                return await import_profile(
                    conn, args.user_id, zip_path=args.linkedin_zip, resume_path=args.resume
                )
        if args.command == "seed":
            return await stage_seed(pool, args.file)
        if args.command == "ingest":
            return await stage_ingest(pool, settings)
        if args.command == "match":
            return await stage_match(pool, args.user_id)
        if args.command == "race":
            return await stage_race(pool, args.user_id, settings)
        if args.command == "work":
            return await stage_work(pool, args.user_id)
        return await run_full_pipeline(pool, args.user_id, settings, seed_path=args.seed_file)
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = asyncio.run(_dispatch(args))
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
