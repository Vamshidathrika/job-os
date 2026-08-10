"""Feedback calibration loop."""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Outcomes that count as the pipeline working, versus wasted effort.
POSITIVE_OUTCOMES = ("interview", "offer")
NEGATIVE_OUTCOMES = ("reject", "ghost")

# Below this many recorded outcomes, differences are noise — hold the weights.
MIN_OUTCOMES_FOR_RECALIBRATION = 20

# Target share of applications that should reach an interview.
TARGET_INTERVIEW_RATE = 0.15
# Largest single step allowed, so one bad week cannot swing the model.
MAX_ADJUSTMENT = 0.10


class CalibrationLoop:
    """Manages the feedback calibration loop to adjust model weights."""

    def __init__(self, conn: Any, tenant_id: str) -> None:
        """Initialize the CalibrationLoop for a specific tenant.

        Args:
            conn: A tenant-scoped connection (see jobos.db.pool.tenant_conn).
            tenant_id: The ID of the tenant.
        """
        self.conn = conn
        self.tenant_id = tenant_id
        self._logger = logger.bind(tenant_id=tenant_id)

    async def record_outcome(self, job_id: str, outcome: str, details: dict[str, Any]) -> None:
        """Record the outcome of a job application process.

        Persisted to agent_decisions so recalibration has real history to read;
        an in-memory record would vanish on restart and the loop would never
        learn anything.

        Args:
            job_id: The ID of the job.
            outcome: The outcome (e.g., apply, interview, offer, reject).
            details: Additional details about the outcome.
        """
        self._logger.info("recording_outcome", job_id=job_id, outcome=outcome)

        await self.conn.execute(
            """
            INSERT INTO agent_decisions (id, user_id, module, action, inputs, outputs)
            VALUES (gen_random_uuid(), $1::uuid, 'calibration', 'record_outcome', $2::jsonb, $3::jsonb)
            """,
            self.tenant_id,
            json.dumps({"job_id": job_id}),
            json.dumps({"outcome": outcome, **details}),
        )

        # Keep the application row in step so the dashboard and the loop agree.
        if outcome in ("interview", "offer", "reject"):
            await self.conn.execute(
                """
                UPDATE applications
                SET status = $2,
                    interview_scheduled_at = CASE
                        WHEN $2 = 'interview' AND interview_scheduled_at IS NULL THEN now()
                        ELSE interview_scheduled_at END
                WHERE job_id = $1::uuid
                """,
                job_id,
                "rejected" if outcome == "reject" else outcome,
            )

    async def recalibrate(self) -> dict[str, Any]:
        """Recalculate model weights based on recorded outcomes.

        Returns:
            Dict containing the adjustments made. All zeros when there is not
            yet enough history to justify moving anything.
        """
        self._logger.info("recalibrating_model_weights")

        counts = await self._outcome_counts()
        total = sum(counts.values())
        if total < MIN_OUTCOMES_FOR_RECALIBRATION:
            self._logger.info("recalibration_skipped_insufficient_data", outcomes=total)
            return {
                "match_threshold_adj": 0.0,
                "ev_weight_adj": 0.0,
                "tier_boundary_adj": {},
                "sample_size": total,
                "reason": "insufficient_data",
            }

        positives = sum(counts.get(o, 0) for o in POSITIVE_OUTCOMES)
        interview_rate = positives / total
        gap = TARGET_INTERVIEW_RATE - interview_rate

        # Under-performing (gap > 0) means we are applying too widely: raise
        # the match threshold to be choosier. Over-performing means we can
        # safely widen the funnel.
        match_threshold_adj = _clamp(gap, MAX_ADJUSTMENT)
        # EV weighting moves opposite the threshold: when results are poor,
        # lean harder on expected value rather than raw similarity.
        ev_weight_adj = _clamp(-gap / 2, MAX_ADJUSTMENT)

        ghost_rate = counts.get("ghost", 0) / total
        tier_boundary_adj = (
            {"tier_1": round(_clamp(ghost_rate, MAX_ADJUSTMENT), 4)} if ghost_rate else {}
        )

        result = {
            "match_threshold_adj": round(match_threshold_adj, 4),
            "ev_weight_adj": round(ev_weight_adj, 4),
            "tier_boundary_adj": tier_boundary_adj,
            "sample_size": total,
            "interview_rate": round(interview_rate, 4),
        }
        self._logger.info("recalibration_complete", **{k: v for k, v in result.items() if k != "tier_boundary_adj"})
        return result

    async def _outcome_counts(self) -> dict[str, int]:
        """Tally recorded outcomes for this tenant."""
        rows = await self.conn.fetch(
            """
            SELECT outputs->>'outcome' AS outcome, count(*) AS n
              FROM agent_decisions
             WHERE module = 'calibration' AND action = 'record_outcome'
             GROUP BY 1
            """
        )
        return {row["outcome"]: row["n"] for row in rows if row["outcome"]}


def _clamp(value: float, limit: float) -> float:
    """Constrain an adjustment to +/- limit."""
    return max(-limit, min(limit, value))
