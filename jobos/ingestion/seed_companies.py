"""Seed the global company universe that the ingestion worker polls."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_companies.yaml"

REQUIRED_FIELDS = ("name", "domain", "ats_type", "ats_identifier")
SUPPORTED_ATS = ("greenhouse", "lever", "ashby", "workday")


async def seed_companies(conn: Any, path: str | None = None) -> dict[str, int]:
    """Upsert the seed company list into the global `companies` table.

    Without this the ingestion worker polls an empty universe and silently
    fetches nothing.

    Args:
        conn: A global (non-tenant) connection — `companies` has no RLS.
        path: Seed YAML; defaults to data/seed_companies.yaml.

    Returns:
        Counts of rows inserted and updated.

    Raises:
        ValueError: if an entry is missing a required field or names an
            unsupported ATS.
    """
    seed_path = Path(path) if path else DEFAULT_SEED_PATH
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    payload = yaml.safe_load(seed_path.read_text()) or {}
    entries = payload.get("companies") or []

    inserted = updated = 0
    for entry in entries:
        for required in REQUIRED_FIELDS:
            if not str(entry.get(required, "")).strip():
                raise ValueError(f"Seed entry {entry!r} is missing {required!r}")
        if entry["ats_type"] not in SUPPORTED_ATS:
            raise ValueError(
                f"Unsupported ats_type {entry['ats_type']!r}; expected one of {SUPPORTED_ATS}"
            )

        was_insert = await conn.fetchval(
            """
            INSERT INTO companies (name, domain, ats_type, ats_identifier)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (domain) DO UPDATE
                SET name = EXCLUDED.name,
                    ats_type = EXCLUDED.ats_type,
                    ats_identifier = EXCLUDED.ats_identifier,
                    updated_at = now()
            RETURNING (xmax = 0)
            """,
            entry["name"],
            entry["domain"],
            entry["ats_type"],
            entry["ats_identifier"],
        )
        if was_insert:
            inserted += 1
        else:
            updated += 1

    logger.info("companies_seeded", inserted=inserted, updated=updated, source=str(seed_path))
    return {"inserted": inserted, "updated": updated}
