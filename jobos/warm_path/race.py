"""Warm-Path 7-Day Race engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from jobos.action_queue.queue import ActionQueue
from jobos.warm_path.channels import WarmPathChannel

logger = structlog.get_logger(__name__)

RACE_DURATION_DAYS = 7

# Race lifecycle.
STATUS_RUNNING = "running"
STATUS_RESOLVED = "resolved"

# How a race ended.
OUTCOME_RUNNING = "running"
OUTCOME_WARM_RESPONSE = "warm_response"
OUTCOME_COLD_APPLY_FALLBACK = "cold_apply_fallback"

TOUCH_ACTION_TYPE = "referral_touch"


class RaceNotStartedError(LookupError):
    """Raised when acting on a race that was never started."""


class WarmPathRace:
    """Manages the 7-day race workflow on multiple channels simultaneously.

    State lives in the warm_path_races table. The race spans a week and is
    advanced by whichever worker happens to be running, so nothing about it
    can be held in process memory.
    """

    def __init__(
        self,
        conn: Any,
        job_id: str,
        tenant_id: str,
        channels: list[str] | None = None,
    ) -> None:
        """Initialize the WarmPathRace.

        Args:
            conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn).
            job_id: The ID of the job.
            tenant_id: The ID of the tenant.
            channels: A list of channels to race on.
        """
        self.conn = conn
        self.job_id = job_id
        self.tenant_id = tenant_id
        self.channels = channels or [c.value for c in WarmPathChannel]
        self._logger = logger.bind(job_id=job_id, tenant_id=tenant_id)
        self._logger.info("initialized_warm_path_race", channels=self.channels)

    async def start_race(self, touches: list[dict[str, Any]] | None = None) -> str:
        """Initiates the 7-day race on multiple channels simultaneously.

        Args:
            touches: Optional outreach sequence, as produced by
                generate_referral_sequence. Each touch is queued at its own
                send_delay_hours so the follow-ups actually land later rather
                than all at once.

        Returns:
            The race id.
        """
        deadline = datetime.now(timezone.utc) + timedelta(days=RACE_DURATION_DAYS)

        race_id = await self.conn.fetchval(
            """
            INSERT INTO warm_path_races (user_id, job_id, status, channels, deadline_at)
            VALUES ($1::uuid, $2::uuid, $3, $4::text[], $5)
            ON CONFLICT (user_id, job_id) DO UPDATE
                SET status = EXCLUDED.status,
                    channels = EXCLUDED.channels,
                    started_at = now(),
                    deadline_at = EXCLUDED.deadline_at,
                    responded_channel = NULL,
                    responded_at = NULL,
                    resolution = NULL,
                    resolved_at = NULL
            RETURNING id
            """,
            self.tenant_id,
            self.job_id,
            STATUS_RUNNING,
            self.channels,
            deadline,
        )

        if touches:
            await self._schedule_touches(str(race_id), touches)

        self._logger.info(
            "started_race", race_id=str(race_id), deadline=deadline.isoformat(), touches=len(touches or [])
        )
        return str(race_id)

    async def _schedule_touches(self, race_id: str, touches: list[dict[str, Any]]) -> None:
        """Queue each touch at its own offset from now."""
        queue = ActionQueue(conn=self.conn, tenant_id=self.tenant_id)
        now = datetime.now(timezone.utc)

        for index, touch in enumerate(touches, start=1):
            delay_hours = float(touch.get("send_delay_hours", 0) or 0)
            await queue.enqueue(
                action_type=TOUCH_ACTION_TYPE,
                payload={
                    "race_id": race_id,
                    "job_id": self.job_id,
                    "touch_number": index,
                    "subject": touch.get("subject", ""),
                    "body": touch.get("body", ""),
                    "to": touch.get("to"),
                },
                # Outreach goes out under review by default; shadow mode and
                # the approval flow decide whether it is promoted to auto.
                band="B",
                scheduled_for=now + timedelta(hours=delay_hours),
            )

    async def record_response(self, channel: str) -> None:
        """Record that a warm path got a reply, ending the race early.

        The first reply wins: later replies do not overwrite which channel
        actually produced the warm path.
        """
        updated = await self.conn.fetchval(
            """
            UPDATE warm_path_races
            SET responded_channel = $2, responded_at = now()
            WHERE job_id = $1::uuid AND responded_at IS NULL
            RETURNING id
            """,
            self.job_id,
            channel,
        )
        if updated is None:
            self._logger.info("response_ignored_race_already_answered", channel=channel)
            return

        # A reply makes every pending touch obsolete — continuing to send
        # follow-ups after someone has replied is the rudest possible bug.
        cancelled = await self.conn.execute(
            """
            UPDATE action_queue
            SET status = 'cancelled', updated_at = now()
            WHERE action_type = $1
              AND status = 'pending'
              AND payload->>'job_id' = $2
            """,
            TOUCH_ACTION_TYPE,
            self.job_id,
        )
        self._logger.info("recorded_warm_response", channel=channel, cancelled_touches=cancelled)

    async def check_response(self, channel: str | None = None) -> bool:
        """Checks if any warm-path channel got a response.

        Args:
            channel: Limit the check to one channel; any channel if omitted.

        Returns:
            True if a response was received, False otherwise.
        """
        race = await self._load()
        if race is None:
            raise RaceNotStartedError(f"No warm path race for job {self.job_id!r}")

        responded = race["responded_at"] is not None
        if responded and channel is not None:
            responded = race["responded_channel"] == channel

        self._logger.info("checking_response", channel=channel, responded=responded)
        return responded

    async def resolve_race(self) -> dict[str, Any]:
        """Returns resolution of the race.

        Returns:
            A dictionary containing outcome, channel, and days_elapsed.
            While the deadline has not passed and no reply has arrived the
            outcome is 'running' — reporting a cold-apply fallback before the
            race is over would release the application the race exists to hold.
        """
        race = await self._load()
        if race is None:
            raise RaceNotStartedError(f"No warm path race for job {self.job_id!r}")

        now = datetime.now(timezone.utc)
        days_elapsed = (now - race["started_at"]).total_seconds() / 86400

        if race["responded_at"] is not None:
            outcome = OUTCOME_WARM_RESPONSE
            channel = race["responded_channel"]
            days_elapsed = (race["responded_at"] - race["started_at"]).total_seconds() / 86400
        elif now < race["deadline_at"]:
            self._logger.info("race_still_running", days_elapsed=round(days_elapsed, 2))
            return {
                "outcome": OUTCOME_RUNNING,
                "channel": None,
                "days_elapsed": round(days_elapsed, 2),
            }
        else:
            outcome = OUTCOME_COLD_APPLY_FALLBACK
            channel = None

        await self.conn.execute(
            """
            UPDATE warm_path_races
            SET status = $2, resolution = $3, resolved_at = COALESCE(resolved_at, now())
            WHERE id = $1
            """,
            race["id"],
            STATUS_RESOLVED,
            outcome,
        )

        self._logger.info("resolved_race", outcome=outcome, channel=channel)
        return {
            "outcome": outcome,
            "channel": channel,
            "days_elapsed": round(days_elapsed, 2),
        }

    async def _load(self) -> Any:
        """Fetch this job's race row, or None."""
        return await self.conn.fetchrow(
            "SELECT * FROM warm_path_races WHERE job_id = $1::uuid", self.job_id
        )


async def find_expired_races(conn: Any, limit: int = 100) -> list[dict[str, Any]]:
    """Races past their deadline with no reply, ready to fall back to cold apply."""
    rows = await conn.fetch(
        """
        SELECT id, job_id, started_at, deadline_at
          FROM warm_path_races
         WHERE status = $1
           AND responded_at IS NULL
           AND deadline_at <= now()
         ORDER BY deadline_at
         LIMIT $2
        """,
        STATUS_RUNNING,
        limit,
    )
    return [
        {
            "race_id": str(row["id"]),
            "job_id": str(row["job_id"]),
            "started_at": row["started_at"],
            "deadline_at": row["deadline_at"],
        }
        for row in rows
    ]
