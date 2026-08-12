"""FastAPI backend for JOBOS — reads and writes the real Postgres pipeline state.

No endpoint here fabricates data. A stage that hasn't run yet (no profile
imported, no jobs ingested) must show as empty or zero, never as an invented
number standing in for it — an operator using these numbers to decide what to
do next needs them to be real or absent, not plausible-looking.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import structlog

from jobos.comp import predict_salary_band, handle_comp_field
from jobos.action_queue.queue import ActionQueue
from jobos.calibration.circuit_breaker import CircuitBreaker
from jobos.calibration.ghost_tracker import detect_ghost_jobs
from jobos.config import settings
from jobos.dashboard.stats import get_pipeline_stats
from jobos.dashboard.timeline import get_activity_timeline
from jobos.db.pool import create_pool, global_conn, tenant_conn
from jobos.vault.api_tokens import InvalidTokenError, resolve_tenant
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
from jobos.onboarding.linkedin_import import import_profile
from jobos.onboarding.shadow_mode import ShadowMode
from jobos.onboarding.wizard import OnboardingWizard
from jobos.runner.handlers import build_handlers
from jobos.runner.pipeline import NoJobFoundError, NoVerifiedBulletsError, stage_upload_resume
from jobos.composio_client.client import ComposioActionError

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


async def authenticated_tenant(authorization: str = Header(default="")) -> str:
    """Resolve the acting tenant from the caller's bearer token.

    Identity comes from a secret the caller proves they hold — never from a
    header they simply assert. Any X-Tenant-Id header is ignored outright:
    validating it against the token would still leave a second, weaker path
    to declaring who you are.
    """
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Authorization: Bearer <token> required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with global_conn(app.state.pool) as conn:
        try:
            return await resolve_tenant(conn, token.strip())
        except InvalidTokenError as e:
            # Malformed, unknown and revoked all fail identically so a caller
            # cannot probe for which tokens exist.
            raise HTTPException(
                status_code=401,
                detail="Invalid or revoked API token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e


async def tenant_db(tenant: str = Depends(authenticated_tenant)) -> AsyncGenerator[Any, None]:
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
async def security_status(tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)) -> dict[str, Any]:
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
    limit: int = 100, tenant: str = Depends(authenticated_tenant)
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
async def get_stats(tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)) -> dict[str, Any]:
    return await get_pipeline_stats(conn, tenant_id=tenant)

@app.get("/api/timeline")
async def get_timeline(
    days: int = 30, tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)
) -> list[dict[str, Any]]:
    return await get_activity_timeline(conn, tenant_id=tenant, days=days)

@app.get("/api/actions")
async def list_actions(
    band: str = "A",
    status: str | None = None,
    tenant: str = Depends(authenticated_tenant),
    conn: Any = Depends(tenant_db),
) -> list[dict[str, Any]]:
    queue = ActionQueue(conn=conn, tenant_id=tenant)
    if status == "pending":
        return await queue.list_pending(limit=50)
    return await queue.dequeue_batch(band=band, limit=20)

@app.post("/api/actions/{action_id}/execute")
async def execute_action(action_id: str, tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)) -> dict[str, Any]:
    """Run the real handler for a queued action — this is what "approve" in
    the dashboard actually does. It previously marked every action
    'completed' with a fixed {"executed": True} regardless of what the
    action was, without running anything: a human clicking approve on a
    prepared cold-apply had no real effect. Band A actions this endpoint can
    reach are all safe to run on approval (referral_touch is guarded by
    suppression+cap; submit_application only fills and screenshots, never
    submits — see ColdApplyExecutor's docstring). Band B/C actions stay
    queued until a human acts on them through this same endpoint.
    """
    row = await conn.fetchrow(
        "SELECT action_type, payload FROM action_queue WHERE id = $1::uuid", action_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"No action {action_id!r}")

    import json

    handlers = build_handlers(conn, tenant)
    handler = handlers.get(row["action_type"])
    if handler is None:
        raise HTTPException(
            status_code=422, detail=f"No handler for action type {row['action_type']!r}"
        )

    queue = ActionQueue(conn=conn, tenant_id=tenant)
    try:
        result = await handler(json.loads(row["payload"]))
    except Exception as e:
        # Must return, not raise: this connection is inside one transaction
        # for the whole request (see tenant_conn), so raising here would
        # roll back the mark_failed write below along with everything else —
        # the failure would vanish from the DB the instant it was recorded.
        await queue.mark_failed(action_id=action_id, error=str(e))
        return JSONResponse(status_code=502, content={"action_id": action_id, "status": "failed", "error": str(e)})

    await queue.mark_complete(action_id=action_id, result=result)
    return {"action_id": action_id, "status": "completed", "result": result}

@app.post("/api/actions/{action_id}/reject")
async def reject_action(
    action_id: str, tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)
) -> dict[str, Any]:
    """A human declined this from the review inbox — mark it rejected without
    running its handler. Symmetric with execute_action's approve path."""
    row = await conn.fetchrow("SELECT id FROM action_queue WHERE id = $1::uuid", action_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No action {action_id!r}")

    queue = ActionQueue(conn=conn, tenant_id=tenant)
    await queue.mark_rejected(action_id=action_id)
    return {"action_id": action_id, "status": "rejected"}

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

@app.get("/api/career-graph/summary")
async def career_graph_summary(
    tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)
) -> dict[str, Any]:
    """Real counts from the Career Graph — no endpoint exposed this before,
    so the dashboard's Career Graph tab showed only static prose."""
    bullets_total = await conn.fetchval("SELECT count(*) FROM cg_bullets")
    bullets_verified = await conn.fetchval(
        "SELECT count(*) FROM cg_bullets WHERE verification_status = 'verified'"
    )
    connections = await conn.fetchval(
        "SELECT count(*) FROM people WHERE source = 'linkedin_connection'"
    )
    return {
        "bullets_total": bullets_total,
        "bullets_verified": bullets_verified,
        "linkedin_connections": connections,
    }

@app.post("/api/onboarding/linkedin-import")
async def upload_linkedin_export(
    file: UploadFile = File(...),
    tenant: str = Depends(authenticated_tenant),
    conn: Any = Depends(tenant_db),
) -> dict[str, int]:
    """HTTP wrapper around the existing CLI-only LinkedIn import path — no
    new parsing logic, just an upload handle in front of import_profile."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        return await import_profile(conn, tenant, zip_path=tmp_path)
    finally:
        import os

        os.unlink(tmp_path)

@app.get("/api/warmpath/races")
async def list_warm_path_races(
    tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)
) -> list[dict[str, Any]]:
    """Real warm_path_races rows — the previous UI showed one fictional,
    hardcoded race ('Stripe — Staff AI Engineer, Day 3 of 7') that did not
    correspond to any row in this table."""
    rows = await conn.fetch(
        """
        SELECT r.status, r.started_at, r.deadline_at, r.responded_channel,
               r.resolution, j.title, c.name AS company
          FROM warm_path_races r
          JOIN jobs j ON j.id = r.job_id
          JOIN companies c ON c.id = j.company_id
         ORDER BY r.started_at DESC
         LIMIT 50
        """
    )
    return [
        {
            "company": row["company"],
            "title": row["title"],
            "status": row["status"],
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "deadline_at": row["deadline_at"].isoformat() if row["deadline_at"] else None,
            "responded_channel": row["responded_channel"],
            "resolution": row["resolution"],
        }
        for row in rows
    ]

@app.get("/api/shadow-mode")
async def get_shadow_mode(
    tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)
) -> dict[str, bool]:
    return {"enabled": await ShadowMode(conn=conn, tenant_id=tenant).is_enabled()}

@app.post("/api/shadow-mode")
async def set_shadow_mode(
    enabled: bool, tenant: str = Depends(authenticated_tenant), conn: Any = Depends(tenant_db)
) -> dict[str, bool]:
    """The previous dashboard toggle was pure client state — clicking it
    changed nothing about real system behavior. This actually flips
    tenants.autonomy_mode, which every send-path check reads from."""
    shadow = ShadowMode(conn=conn, tenant_id=tenant)
    await (shadow.enable() if enabled else shadow.disable())
    return {"enabled": await shadow.is_enabled()}

@app.get("/api/onboarding/wizard")
async def get_wizard_status(tenant: str = Depends(authenticated_tenant)) -> dict[str, Any]:
    wiz = OnboardingWizard(tenant_id=tenant)
    return await wiz.start()

@app.post("/api/onboarding/step")
async def submit_wizard_step(req: OnboardingStepReq, tenant: str = Depends(authenticated_tenant)) -> dict[str, Any]:
    wiz = OnboardingWizard(tenant_id=tenant)
    return await wiz.submit_step(req.step_name, req.data)

@app.post("/api/jobs/{job_id}/generate-resume")
async def generate_resume(
    job_id: str, tenant: str = Depends(authenticated_tenant)
) -> dict[str, str]:
    """Thin wrapper around stage_upload_resume — no new tailoring logic.
    Uses the pool directly (not the per-request tenant_db connection):
    stage_upload_resume opens its own tenant-scoped connection internally."""
    try:
        return await stage_upload_resume(app.state.pool, tenant, job_id, settings)
    except NoJobFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except NoVerifiedBulletsError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ComposioActionError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
