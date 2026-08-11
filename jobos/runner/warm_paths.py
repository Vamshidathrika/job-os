"""Turn Tier-1 matches into warm-path races.

Referrers come from the operator's own LinkedIn connections rather than a
paid people-search API: Connections.csv already lists everyone they know and
where those people work.
"""

from __future__ import annotations

from typing import Any

import structlog

from jobos.referral.network_mapper import map_existing_network
from jobos.referral.sequence import generate_referral_sequence
from jobos.warm_path.decision import should_hold_application
from jobos.warm_path.race import WarmPathRace

logger = structlog.get_logger(__name__)


async def start_races_for_tier_1(
    conn: Any, user_id: str, settings: Any = None, limit: int = 20
) -> dict[str, int]:
    """Start a warm-path race for each Tier-1 match that has a warm contact.

    Args:
        conn: A tenant-scoped connection.
        user_id: The acting user.
        settings: Application settings, forwarded to sequence generation.
        limit: Maximum races to start in one pass.

    Returns:
        started — races begun;
        no_warm_path — Tier-1 jobs where the operator knows nobody;
        gated — contacts dropped by the personalisation gate.
    """
    candidates = await conn.fetch(
        """
        SELECT m.job_id, m.score, m.ev_score, m.tier, j.title, c.name AS company_name, c.domain
          FROM matches m
          JOIN jobs j ON j.id = m.job_id
          JOIN companies c ON c.id = j.company_id
          LEFT JOIN warm_path_races r ON r.job_id = m.job_id
         WHERE m.tier = 1 AND r.id IS NULL
         ORDER BY m.ev_score DESC
         LIMIT $1
        """,
        limit,
    )

    contacts = [
        dict(row)
        for row in await conn.fetch(
            "SELECT full_name, company_domain, email, title, source FROM people WHERE user_id = $1::uuid",
            user_id,
        )
    ]

    started = no_warm_path = gated = 0

    for candidate in candidates:
        if not should_hold_application(
            match_score=candidate["score"], ev_score=candidate["ev_score"], tier=candidate["tier"]
        ):
            continue

        company = candidate["company_name"] or candidate["domain"]
        # map_existing_network stamps its own "source": "existing_network" onto
        # every warm lead it returns, overwriting whatever came in under that
        # key. Carry the real people.source (e.g. "linkedin_connection") in
        # under a different key so it survives the round trip.
        warm = await map_existing_network(
            [
                {**c, "company": c["company_domain"], "contact_source": c["source"]}
                for c in contacts
            ],
            [company],
        )

        reachable = [w for w in warm if w.get("email")]
        if not reachable:
            no_warm_path += 1
            logger.info("no_warm_path_available", job_id=str(candidate["job_id"]), company=company)
            continue

        referrer = reachable[0]
        touches = await generate_referral_sequence(
            referrer={
                "name": referrer.get("full_name"),
                "title": referrer.get("title"),
                "company_domain": referrer.get("company_domain"),
                # A mutual employer is the shared context that clears the gate.
                "shared_past_company": [company] if referrer.get("contact_source") == "linkedin_connection" else [],
            },
            job={"title": candidate["title"], "company": company},
            user_profile={"name": "the candidate"},
            settings=settings,
        )

        if not touches:
            gated += 1
            logger.info("referral_gated", job_id=str(candidate["job_id"]), company=company)
            continue

        for touch in touches:
            touch["to"] = referrer["email"]

        race = WarmPathRace(conn=conn, job_id=str(candidate["job_id"]), tenant_id=user_id)
        await race.start_race(touches=touches)
        started += 1

    logger.info(
        "tier_1_races_processed", started=started, no_warm_path=no_warm_path, gated=gated
    )
    return {"started": started, "no_warm_path": no_warm_path, "gated": gated}
