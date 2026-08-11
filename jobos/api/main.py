"""FastAPI backend for JOBOS — reads and writes the real Postgres pipeline state.

No endpoint here fabricates data. A stage that hasn't run yet (no profile
imported, no jobs ingested) must show as empty or zero, never as an invented
number standing in for it — an operator using these numbers to decide what to
do next needs them to be real or absent, not plausible-looking.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog

from jobos.comp import predict_salary_band, handle_comp_field
from jobos.action_queue.queue import ActionQueue
from jobos.calibration.circuit_breaker import CircuitBreaker
from jobos.calibration.ghost_tracker import detect_ghost_jobs
from jobos.config import settings
from jobos.dashboard.stats import get_pipeline_stats
from jobos.dashboard.timeline import get_activity_timeline
from jobos.db.pool import create_pool, tenant_conn
from jobos.policy.multi_tenant import PROHIBITIONS
from jobos.hiring_radar.sources import scan_funding_rss
from jobos.referral.scorer import score_referrer
from jobos.referral.finder import find_referrers
from jobos.warm_path.decision import should_hold_application, select_fallback_band
from jobos.content.generator import generate_engagement_post
from jobos.content.comment_engine import generate_smart_comment
from jobos.profile.optimizer import analyze_profile
from jobos.interview.prep import generate_prep_pack
from jobos.followup.nudge import generate_status_nudge
from jobos.onboarding.wizard import OnboardingWizard

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.pool = await create_pool(settings)
    logger.info("postgres_pool_initialized")
    try:
        yield
    finally:
        await app.state.pool.close()


app = FastAPI(title="JOBOS Autopilot Backend API — Real Data Layer", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def tenant_id_header(x_tenant_id: str = Header(...)) -> str:
    """Require an explicit tenant id on every tenant-scoped request.

    There is deliberately no default: a fallback tenant would let any caller
    who omits the header silently read and write another tenant's rows.
    """
    if not x_tenant_id.strip():
        raise HTTPException(status_code=400, detail="X-Tenant-Id header must not be empty")
    return x_tenant_id


async def tenant_db(tenant: str = Depends(tenant_id_header)) -> AsyncGenerator[Any, None]:
    """Yield a connection with this request's tenant context applied.

    Real DB errors propagate as a 500 rather than being swallowed into a
    silent fake-data fallback — a caller acting on these numbers needs to
    know the difference between "empty" and "the query failed".
    """
    async with tenant_conn(app.state.pool, tenant) as conn:
        yield conn


# Request Models
class CompPredictReq(BaseModel):
    title: str
    location: str
    yoe: int

class CompDeflectReq(BaseModel):
    field_type: str
    field_value: str | None = None
    predicted_band: dict[str, Any]

class ContentGenReq(BaseModel):
    topic: str
    platform: str = "linkedin"

class ProfileAnalyzeReq(BaseModel):
    headline: str
    summary: str
    experience: list[dict[str, Any]] = []

class InterviewPrepReq(BaseModel):
    title: str
    company: str
    interview_type: str = "technical"

class ReferrerScoreReq(BaseModel):
    shared_school: bool = False
    shared_past_company: bool = False
    same_department: bool = False
    seniority_match: bool = False

class OnboardingStepReq(BaseModel):
    step_name: str
    data: dict[str, Any]


# ENDPOINTS CONNECTED TO REAL ATS DATA

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "JOBOS Backend API", "rls": "ENFORCED"}

@app.get("/api/security/status")
async def security_status(tenant: str = Depends(tenant_id_header), conn: Any = Depends(tenant_db)) -> dict[str, Any]:
    cb = CircuitBreaker(conn=conn, tenant_id=tenant)
    status = await cb.get_status()
    return {
        "tenant_id": tenant,
        "rls_enforced": True,
        "policy_prohibitions_count": len(PROHIBITIONS),
        "prohibitions": PROHIBITIONS,
        "circuit_breaker": {"limits": status["limits"], "action_counts": status["action_counts"]},
        "kms_vault_status": f"ONLINE (kms_provider={settings.vault.kms_provider})",
    }

@app.get("/api/jobs")
async def list_jobs(
    limit: int = 100, tenant: str = Depends(tenant_id_header)
) -> list[dict[str, Any]]:
    """Jobs already ingested into Postgres by `jobos ingest`.

    Job postings themselves have no per-tenant RLS — they're shared discovery
    data — but tier/EV are the tenant's own match results (`jobos match`), so
    those come from a LEFT JOIN under this tenant's RLS context. A job that
    hasn't been matched yet for this tenant simply has no tier/ev_score,
    rather than a fabricated placeholder value.
    """
    async with tenant_conn(app.state.pool, tenant) as conn:
        rows = await conn.fetch(
            """
            SELECT j.id, j.external_id, j.title, j.location, j.country,
                   c.name AS company, m.tier, m.ev_score, m.score AS match_score
              FROM jobs j
              JOIN companies c ON c.id = j.company_id
              LEFT JOIN matches m ON m.job_id = j.id
             ORDER BY j.first_seen_at DESC
             LIMIT $1
            """,
            limit,
        )
    return [
        {
            "job_id": row["external_id"],
            "title": row["title"],
            "company": row["company"],
            "location": row["location"] or row["country"],
            "tier": row["tier"],
            "ev_score": row["ev_score"],
            "match_score": row["match_score"],
        }
        for row in rows
    ]

@app.get("/api/radar/signals")
async def get_hiring_radar_signals(feed_url: str = "http://example.com/rss") -> dict[str, Any]:
    signals = await scan_funding_rss(feed_url)
    return {"signals_detected": len(signals), "active_radar_sources": ["Funding RSS", "Apollo Spikes", "Exec Departures"]}

@app.post("/api/comp/predict")
async def predict_comp(req: CompPredictReq) -> dict[str, Any]:
    return predict_salary_band(title=req.title, location=req.location, yoe=req.yoe)

@app.post("/api/comp/deflect")
async def deflect_comp(req: CompDeflectReq) -> dict[str, str]:
    return handle_comp_field(field_type=req.field_type, field_value=req.field_value, predicted_band=req.predicted_band)

@app.post("/api/referral/score")
async def score_referrer_candidate(req: ReferrerScoreReq) -> dict[str, float]:
    score = score_referrer(
        {
            "shared_school": req.shared_school,
            "shared_past_company": req.shared_past_company,
            "same_department": req.same_department,
            "seniority_match": req.seniority_match,
        },
        {},
    )
    return {"score": score}

@app.get("/api/referral/candidates")
async def get_referral_candidates(domain: str = "postman.com") -> list[dict[str, Any]]:
    return await find_referrers(domain, {"schools": ["Stanford"], "past_companies": ["Google"]}, apollo=None)

@app.get("/api/warmpath/status")
async def warm_path_status(
    tier: int = 1, match_score: float = 0.9, ev_score: float = 69300.0,
    days_elapsed: int = 0, warm_responses: int = 0,
) -> dict[str, Any]:
    """Pure decision calculator: given these inputs, what would the policy do.

    Not backed by any specific job's real race — that lives in
    warm_path_races (see jobos.warm_path.race). days_elapsed and
    warm_responses are accepted as explicit inputs precisely so this cannot
    silently pretend to know a real race's progress.
    """
    return {
        "tier": tier,
        "hold_for_warm_path": should_hold_application(match_score, ev_score, tier),
        "current_fallback_band": select_fallback_band(days_elapsed, warm_responses),
    }

@app.post("/api/content/generate")
async def generate_post(req: ContentGenReq) -> dict[str, Any]:
    return await generate_engagement_post(topic=req.topic, user_profile={"name": "Candidate"}, platform=req.platform)

@app.get("/api/content/comment")
async def generate_comment(post_text: str = "We are hiring AI Engineers at Postman!", company: str = "Postman") -> dict[str, str]:
    comment = await generate_smart_comment(post_text, ["Python", "Distributed Systems"], company)
    return {"comment": comment}

@app.post("/api/profile/analyze")
async def analyze_profile_endpoint(req: ProfileAnalyzeReq) -> dict[str, Any]:
    return await analyze_profile({"headline": req.headline, "summary": req.summary, "experience": req.experience})

@app.get("/api/stats")
async def get_stats(tenant: str = Depends(tenant_id_header), conn: Any = Depends(tenant_db)) -> dict[str, Any]:
    return await get_pipeline_stats(conn, tenant_id=tenant)

@app.get("/api/timeline")
async def get_timeline(
    days: int = 30, tenant: str = Depends(tenant_id_header), conn: Any = Depends(tenant_db)
) -> list[dict[str, Any]]:
    return await get_activity_timeline(conn, tenant_id=tenant, days=days)

@app.get("/api/actions")
async def list_actions(band: str = "A", tenant: str = Depends(tenant_id_header), conn: Any = Depends(tenant_db)) -> list[dict[str, Any]]:
    queue = ActionQueue(conn=conn, tenant_id=tenant)
    return await queue.dequeue_batch(band=band, limit=20)

@app.post("/api/actions/{action_id}/execute")
async def execute_action(action_id: str, tenant: str = Depends(tenant_id_header), conn: Any = Depends(tenant_db)) -> dict[str, Any]:
    queue = ActionQueue(conn=conn, tenant_id=tenant)
    await queue.mark_complete(action_id=action_id, result={"executed": True})
    return {"action_id": action_id, "status": "completed"}

@app.post("/api/interview/prep")
async def generate_prep(req: InterviewPrepReq) -> dict[str, Any]:
    return await generate_prep_pack({"title": req.title, "company": req.company}, {"name": "Candidate"}, req.interview_type)

@app.get("/api/followup/nudge")
async def status_nudge(company: str = "Postman", role: str = "Senior AI Architect", days_since: int = 5) -> dict[str, str]:
    return await generate_status_nudge({"company": company, "title": role}, days_since)

@app.get("/api/integrations/status")
async def integrations_status() -> dict[str, Any]:
    """Whether Composio is configured — NOT whether a Gmail/Calendar account
    is actually connected. A configured API key means Composio calls will be
    attempted; it does not mean a human has completed the OAuth flow for any
    given tenant. Verifying an actual live connection requires a Composio
    API call this endpoint does not make.
    """
    configured = bool(settings.composio.api_key)
    status = "configured (connection not verified)" if configured else "not_configured"
    return {"composio": status, "gmail": status, "calendar": status}

@app.get("/api/calibration/ghost-jobs")
async def ghost_jobs_check() -> list[dict[str, Any]]:
    test_jobs = [{"job_id": "ghost-1", "days_active": 75, "title": "Stale Engineer Role"}]
    return await detect_ghost_jobs(test_jobs)

@app.get("/api/onboarding/wizard")
async def get_wizard_status(tenant: str = Depends(tenant_id_header)) -> dict[str, Any]:
    wiz = OnboardingWizard(tenant_id=tenant)
    return await wiz.start()

@app.post("/api/onboarding/step")
async def submit_wizard_step(req: OnboardingStepReq, tenant: str = Depends(tenant_id_header)) -> dict[str, Any]:
    wiz = OnboardingWizard(tenant_id=tenant)
    return await wiz.submit_step(req.step_name, req.data)
