"""Scheduler for content posting."""
from __future__ import annotations

import json
import random
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import structlog

from jobos.config import Settings, settings as default_settings

logger = structlog.get_logger(__name__)

# Windows where professional audiences are actually reading, in the viewer's
# local time. Weekday mid-morning and just after lunch outperform evenings.
PEAK_HOURS_BY_PLATFORM = {
    "linkedin": (10, 13),
    "twitter": (9, 17),
}
DEFAULT_PEAK_HOURS = (10, 13)


class ContentScheduler:
    """
    Schedules content posts taking into account platform rules and tenant policies.
    """

    def __init__(self, conn: Any, tenant_id: str, settings: Settings | None = None) -> None:
        """
        Initialize the ContentScheduler with a tenant ID.

        WHAT: Sets up the scheduler context for a specific tenant.
        WHY: Schedules are tenant-specific and need to respect individual tenant policies and rate limits.

        Args:
            conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn).
            tenant_id: The tenant whose queue receives the scheduled post.
            settings: Application settings; defaults to the global singleton.
        """
        self.conn = conn
        self.tenant_id = tenant_id
        self.settings = settings or default_settings
        logger.info("initialized_content_scheduler", tenant_id=tenant_id)

    async def schedule_post(
        self, content: dict[str, Any], platform: str, publish_at: datetime
    ) -> dict[str, Any]:
        """
        Queue a post for publication at a specific time.

        WHAT: Persists the post to the action queue.
        WHY: To allow asynchronous execution and ensure posts go out at optimal times.

        The returned post_id is the real queue row id, so a caller can look the
        post up, cancel it, or check whether it actually published.
        """
        logger.info(
            "scheduling_post",
            tenant_id=self.tenant_id,
            platform=platform,
            publish_at=publish_at.isoformat(),
        )

        payload = {**content, "platform": platform, "publish_at": publish_at.isoformat()}
        post_id = await self.conn.fetchval(
            """
            INSERT INTO action_queue (user_id, action_type, payload, band, status)
            VALUES ($1::uuid, 'publish_post', $2::jsonb, 'B', 'pending')
            RETURNING id
            """,
            self.tenant_id,
            json.dumps(payload),
        )

        logger.info("post_scheduled", tenant_id=self.tenant_id, post_id=str(post_id))
        return {
            "post_id": str(post_id),
            "status": "scheduled",
            "publish_at": publish_at.isoformat(),
        }

    def get_optimal_time(self, platform: str, timezone_name: str = "Asia/Kolkata") -> datetime:
        """
        Determine the best posting time for a given platform and timezone.

        WHAT: Calculates the next in-window weekday slot, with jitter.
        WHY: Posting at the right time increases reach — and identical daily
             timings are a strong automation signal, so the slot is jittered
             and weekends are skipped per the LinkedIn policy.
        """
        logger.info(
            "calculating_optimal_time",
            tenant_id=self.tenant_id,
            platform=platform,
            timezone=timezone_name,
        )

        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            logger.warning("unknown_timezone_falling_back_to_utc", timezone=timezone_name)
            tz = timezone.utc

        start_hour, end_hour = PEAK_HOURS_BY_PLATFORM.get(platform.lower(), DEFAULT_PEAK_HOURS)
        jitter = timedelta(minutes=random.randint(0, self.settings.linkedin.jitter_max_minutes))

        now_local = datetime.now(tz)
        candidate = datetime.combine(now_local.date(), time(hour=start_hour), tzinfo=tz) + jitter

        # Always schedule ahead of now, inside the window, on a weekday.
        if candidate <= now_local or candidate.hour >= end_hour:
            candidate = datetime.combine(
                now_local.date() + timedelta(days=1), time(hour=start_hour), tzinfo=tz
            ) + jitter
        while candidate.weekday() >= 5:  # Saturday/Sunday
            candidate += timedelta(days=1)

        return candidate.astimezone(timezone.utc)
