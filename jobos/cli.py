"""JOBOS command line entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import structlog

from jobos.config import settings
from jobos.db.pool import create_pool, global_conn, tenant_conn
from jobos.vault.api_tokens import create_token, list_tokens, revoke_token
from jobos.runner.pipeline import (
    run_full_pipeline,
    stage_ingest,
    stage_match,
    stage_race,
    stage_seed,
    stage_upload_resume,
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

    resume = sub.add_parser("resume", help="Tailor a resume for one job and save it to Drive")
    resume.add_argument("--job-id", required=True)

    run = sub.add_parser("run", help="Run the whole pipeline")
    run.add_argument("--seed-file")

    token = sub.add_parser("token", help="Manage API tokens for the dashboard/API")
    token_sub = token.add_subparsers(dest="token_action", required=True)
    token_create = token_sub.add_parser("create", help="Mint a token (shown once)")
    token_create.add_argument("--name", required=True, help="Label, e.g. 'laptop'")
    token_sub.add_parser("list", help="List tokens (never shows the secret)")
    token_revoke = token_sub.add_parser("revoke", help="Revoke a token by name")
    token_revoke.add_argument("--name", required=True)

    return parser


async def run_token_command(
    pool: Any, user_id: str, action: str, name: str | None = None
) -> dict[str, Any]:
    """Create, list or revoke API tokens.

    api_tokens has no RLS — authentication has to resolve a tenant before a
    tenant context exists — so this runs on a global connection.
    """
    async with global_conn(pool) as conn:
        if action == "create":
            token = await create_token(conn, user_id, name=name or "")
            return {
                "token": token,
                "name": name,
                "warning": "Store this now — it is hashed at rest and cannot be shown again.",
            }
        if action == "revoke":
            return {"revoked": await revoke_token(conn, user_id, name=name or ""), "name": name}
        return {"tokens": await list_tokens(conn, user_id)}


async def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    pool = await create_pool(settings)
    try:
        if args.command == "import":
            from jobos.onboarding.linkedin_import import import_profile

            async with tenant_conn(pool, args.user_id) as conn:
                return await import_profile(
                    conn, args.user_id, zip_path=args.linkedin_zip, resume_path=args.resume
                )
        if args.command == "token":
            return await run_token_command(
                pool, args.user_id, action=args.token_action, name=getattr(args, "name", None)
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
        if args.command == "resume":
            return await stage_upload_resume(pool, args.user_id, args.job_id, settings)
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
