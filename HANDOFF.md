# JOBOS — Handoff / Project State

**Last updated:** 2026-08-12, by Claude (session covering commits `148b892` → `2689f4a`, plus an in-flight auth-hardening agent not yet landed — check `git log --oneline -5` before trusting the auth section below)

Read this before touching the repo. It exists because **multiple agent
sessions have worked on this codebase concurrently and at least once directly
reverted a security fix** (see "Known collision history" below). If you are a
fresh agent picking this up: `git log --oneline -20`, diff against what this
doc describes, and do not assume the state below still matches reality.

---

## What this project is

Autonomous warm-path job search engine. Thesis: cold applications convert
~3%, a real referral converts ~40%. The system races a 7-day "warm path"
(referral → recruiter → signal) before falling back to cold apply, gated by
an entailment verifier so nothing fabricated gets sent to an employer.

Full product framing: [`README.md`](README.md).

## Where things stand right now

**359 tests passing** as of `2689f4a` (before the auth-hardening agent's new
tests land — re-run and update this number once they do).
`python -m pytest tests/ -q` from repo root (`.venv` must be active, see
Environment below).

### What is real and working end-to-end

- **Job ingestion** — polls public Greenhouse/Lever/Ashby boards, no API key
  needed. Verified live: pulled 108 real postings from Postman's board.
- **Matching pipeline** — scores ingested jobs against a Career Graph using
  local embeddings (no key), writes real `matches` rows with score/EV/tier.
- **Warm-path race** — durable DB-backed 7-day state machine
  (`warm_path_races` table). Sources referrers from the operator's own
  LinkedIn connections (imported via `jobos import`), not a paid API.
- **Entailment gate** — real LLM verifier call, but has zero production
  callers anywhere in the pipeline yet — nothing invokes it before tailored
  text would go out. Also routes through `entailment_model` (nvidia_nim),
  a provider with no configured key and no wiring (see `b880b68`'s fix,
  which deliberately left this one alone).
- **LLM key wiring** — `settings.llm.platform_groq_key` is now actually
  passed to every `acompletion()` call (8 of 9 sites; entailment is the
  exception above). It previously existed in config and was never passed
  anywhere, so every call silently relied on an unset `GROQ_API_KEY` env
  var, failed, and — worse — in the warm-path race, that failure was
  counted as `gated` (personalization gate rejection), indistinguishable
  from healthy behaviour. Fixed and split into `gated` vs `llm_failed` at
  `b880b68`. Verified live: with no real key configured, `jobos race` now
  correctly reports `llm_failed=20, gated=0` with a real
  `litellm.BadRequestError` from Groq's actual API in the log — proof the
  code is right and the only missing piece is the key value itself, which
  must go in `.env` directly, never pasted into a chat session.
- **Tier-1 classification was unreachable.** `classify_tier` requires
  `match_score>=0.65 AND ev_score>=0.60`, but `ev_score` was derived from
  `EV = p_offer * comp * p_accept` where `p_offer = match_score * 0.35` —
  so it re-embedded match_score and was capped at 0.35 by construction. A
  0.9 match on the best comp band scored `ev_score=0.27`. No Tier-1 job
  could ever exist, so the warm-path race — which only fires on Tier 1 —
  could never start, for any profile, ever. Fixed at `b880b68`: `ev_score`
  now measures value alone (comp normalised), independent of match
  quality. Verified live against a real imported profile: 65 of 108 jobs
  now correctly classify as Tier 1.
- **Guarded send path** — suppression list + daily cap enforced in front of
  any outbound email; shadow mode on by default (queues to Band B for human
  approval, never auto-sends).
- **CLI orchestrator** — `jobos` command, installed via
  `[project.scripts]`. Runs the whole pipeline or any single stage.
- **Dashboard API** — as of `ce65019`, every endpoint reads real Postgres
  state. No endpoint fabricates a fallback number anymore.
- **Dashboard UI redesigned around the actual job-search workflow**
  (`de1d829`). The old UI was 15 tabs named after backend modules ("Phase 3:
  Matcher & EV Ranker") — the user found it unusable ("what are that 15
  buttons why i will click them"). Replaced with a 6-item sidebar (Profile
  & LinkedIn, Job Matches, Applications, Referrals, Interview Prep,
  Calendar & Integrations) plus a global "Needs your review" inbox where
  every send/apply/schedule action still requires explicit human
  approve/reject — that gating is a standing user decision, not a default,
  see "Recommended next steps" history below. Spec:
  `docs/superpowers/specs/2026-08-12-workflow-dashboard-design.md`. Plan
  (has exact code for every file, useful if this needs touching again):
  `docs/superpowers/plans/2026-08-12-workflow-dashboard.md`. Built via 10
  tasks across 2 waves of parallel subagents — worked cleanly; the only
  friction was 3 agents racing on the same `jobos/api/main.py` file for
  independent endpoint additions, which git handled fine (each agent's
  intended diff survived, verified by rereading the file and rerunning the
  full suite — 359 passed) but cost some agent turns re-checking "is my
  diff still mine."
- **Google Drive integration + real cold-apply form-filling** (`148b892`).
  `jobos/integrations/drive.py` uploads tailored resumes to a
  `JOBOS Resumes` Drive folder via Composio. `jobos/cold_apply/executor.py`
  uses real Playwright to fill a real application form and screenshot it —
  **it never clicks Submit, under any circumstance, including after human
  approval in the dashboard.** This was an explicit user decision (asked via
  AskUserQuestion: "Review, then I approve each one" over full autonomy) —
  do not build an auto-submit path without that conversation happening
  again. Finishing the actual submission is the operator's own action in
  their own browser; the artifact this produces (filled fields +
  screenshot) is the deliverable.
- **4 new API endpoints** (`b2b2556`, `fcd1e24`, `bbc079e`): pending-actions
  list + reject (backs the review inbox), LinkedIn export upload (HTTP
  wrapper around the CLI-only importer), resume-generate (HTTP wrapper
  around `stage_upload_resume`). All have integration tests — see
  "`jobos/api/main.py` has zero test coverage" below, which is now
  partially, not fully, stale.
- **Seed company ATS tokens fixed** (`2689f4a`). The previous "3 of 8
  broken" claim below undercounted: verified live against the exact request
  pattern `jobos/ingestion/poller.py` uses, 7 of 8 original entries were
  dead (404, or 200-with-zero-jobs for a since-abandoned tenant). Replaced
  with 4 verified-live boards: Postman, Groww, CRED, Meesho. If re-adding a
  company, verify the same way — hit the real endpoint and check it returns
  that company's actual jobs, not just a 200; a wrong-but-live token risks
  silently seeding a different company's postings under this one's name.

### What is explicitly NOT implemented (raises `NotImplementedError`, on purpose)

- **GCP KMS** (`jobos/vault/kms.py`) — AWS KMS is implemented; GCP raises.
  Shipping a silent stub here would mean tenant DEKs were never wrapped.
- **LinkedIn publishing** (`jobos/runner/handlers.py::publish_post`) — no
  Composio LinkedIn connection wired up yet.
- **Cold-apply auto-submit** — see above. This is a deliberate, standing
  product decision (human approves every application), not a gap to close.

### What is NOT done and is the biggest real gap

- ~~**API has no authentication.**~~ **Done** (`6515dea`). Tenant identity now
  comes from an opaque bearer token, hashed at rest in `api_tokens`.
  `X-Tenant-Id` is ignored outright. Mint with
  `jobos --user-id <uuid> token create --name browser`; the dashboard has a
  paste-once login screen. `/health` stays public.
  **Auth hardening (token expiry, rate limiting on failed auth, audit
  trail) was in progress via a background agent as this doc was last
  updated — check `git log` for commits after `2689f4a` mentioning "auth"
  before assuming this is still open.**
- ~~**No LLM path has been run against a real model.**~~ **Code-level fix
  done** (`b880b68`) — key wiring was the actual bug (see above), verified
  down to a real rejected call from Groq's live API. Still blocked on the
  user's real key landing in `.env`; nobody has typed a real key value
  into this repo. All LLM-dependent code remains unit-tested against
  mocked responses only until that happens.
- **No real LinkedIn export has been imported.** The importer
  (`jobos/onboarding/linkedin_import.py`) is built and tested against a
  synthetic fixture ZIP, and now also reachable from the dashboard's
  Profile page via upload, but the user's real export hasn't landed yet.
- **`jobos/api/main.py` test coverage is partial, not zero.** The 4 newest
  endpoints (pending-actions, reject, linkedin-import, generate-resume) have
  integration tests. Older endpoints (stats, jobs, comp, content, profile,
  security/status, career-graph/summary, warmpath/races, shadow-mode,
  onboarding/wizard) still don't — every "real" claim about those was
  verified by manual `curl`/browser screenshot, not an automated test.

---

## Known collision history — read before assuming anything

This repo had **two agent sessions working on it concurrently** for at least
part of this history. Evidence and what happened:

- At `a701461` (mine), the tree was clean at 283 tests. Four commits then
  landed that I did not make: `c8730ba`, `c47fe82`, `8c04f1b`, `29ba570` —
  an 809-line dashboard rewrite and a 399-line `api/main.py` rewrite
  ("15-phase master control panel").
- One of those commits (`c47fe82`) **directly reverted two fixes** I had
  made earlier in the same session:
  1. `jobos/referral/finder.py` — reintroduced a fabricated referrer
     fallback (fake email `referral@<domain>`, invented "Stanford"/"Google"
     shared history) when no Apollo client was configured — the exact bug
     this project's own docstrings warn against.
  2. `jobos/api/main.py` — reintroduced a default tenant UUID on the
     `X-Tenant-Id` header, i.e. a tenant-impersonation hole.
- Both were re-fixed at `586e3fd`, with a regression test added that names
  the specific fabricated string so it can't silently come back a third
  time (`tests/unit/test_referral_engine.py::test_finder_returns_nothing_when_no_apollo_client_configured`).
- Separately, that same rewrite introduced an `api/main.py` full of silent
  fake-data fallbacks (hardcoded "14 applications sent", "CONNECTED" Gmail
  status with no Composio key configured, etc.) — fixed at `ce65019`.

**If you see a diff you didn't make:** don't assume it's safe. Check whether
it reintroduces a fabrication, an auth bypass, or a silent-fallback pattern.
Grep for `except Exception:\s*pass` and hardcoded-looking literals as a first
pass — that pattern is exactly what caused both regressions above.

**Second collision, benign this time:** while committing `b880b68`, found 4
of the 8 files it touches (`comment_engine.py`, `interview/prep.py`,
`profile/optimizer.py`, `tailorer/generator.py`) already carried the
identical `api_key=settings.llm.platform_groq_key or None` fix from a
concurrent session — same diagnosis, same fix, independently, almost
certainly because both sessions read the same gap list in this file. No
conflict, nothing reverted. Worth noting as the flip side of the warning
above: concurrent sessions reading this doc converge, they don't only
collide.

---

## Environment / how to run things

```bash
cd /Users/nani/Downloads/primeneuro/jobos
source .venv/bin/activate
```

- **Postgres:** local, role `jobos` (non-superuser — RLS does not apply to
  superusers, so it must stay non-superuser or the isolation tests become
  meaningless), database `jobos` (dev) and `jobos_test` (test). pgvector
  extension must be present; the app role cannot `CREATE EXTENSION` itself
  (needs a superuser once, already done).
- **`.env`** exists locally (gitignored, not in the repo) with
  `JOBOS_VAULT_LOCAL_MASTER_KEY_HEX` and DB connection settings. If this file
  is missing, defaults in `jobos/config.py` mostly work for local dev except
  the vault master key (has an insecure default — fine for dev, must be
  replaced before anything resembling production).
- **Run the pipeline:**
  ```bash
  jobos --user-id <uuid> seed          # upsert data/seed_companies.yaml
  jobos --user-id <uuid> ingest        # poll public ATS boards
  jobos --user-id <uuid> match         # score jobs against Career Graph
  jobos --user-id <uuid> race          # start/resolve warm-path races
  jobos --user-id <uuid> work          # execute due Band A actions
  jobos --user-id <uuid> run           # all of the above in order
  jobos --user-id <uuid> import --linkedin-zip <path> --resume <path>
  ```
  A `tenants`/`users` row must exist for `<uuid>` first (FK constraint) —
  see `docs/superpowers/plans/2026-08-10-first-real-run.md` Task 2 for the
  importer, or insert manually for a demo tenant.
- **API backend:** `python -m uvicorn jobos.api.main:app --port 8000`
- **Dashboard:** `npm --prefix dashboard run dev` (proxies `/api` to
  `localhost:8000`, see `dashboard/vite.config.ts`). Note: there is a
  **parent-directory** `.claude/launch.json` at
  `/Users/nani/Downloads/primeneuro/.claude/launch.json` that points
  `npm run dev` at an unrelated project one level up (a different app
  entirely, not jobos). This repo's own `.claude/launch.json` (added this
  session) is shadowed by it when using the `preview_start` tool with a
  `name` — start the dashboard dev server directly instead, or fix the
  parent config if you want `preview_start` to work by name.

## Key documents

- Design spec: `docs/superpowers/specs/2026-08-10-first-real-run-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-10-first-real-run.md`
  (7 tasks, dependency-ordered waves, exact code for each step — useful
  reference for how the matching pipeline / race wiring / CLI fit together)
- This file: living document, update it when you finish a unit of work or
  hand off to someone/something else.

## Recommended next steps, in priority order

1. **Get a real Groq key into `.env`.** The code bug is fixed (`b880b68`);
   this is now purely a credential problem. `JOBOS_LLM_PLATFORM_GROQ_KEY=`
   in `.env` — never paste the key value into a chat session, type it
   directly into the file. Then `jobos --user-id <uuid> run` end to end.
   **Blocked on the user, not on code — nothing to build here.**
2. **Get the user's real LinkedIn export imported.** The upload path exists
   now (dashboard Profile page, or `jobos import --linkedin-zip <path>`);
   nobody has run it against real data yet. Also blocked on the user, not
   code.
3. **Verify live Composio OAuth connections**, not just that a key is
   configured. `GET /api/integrations/status` today only reports whether
   `COMPOSIO_API_KEY` is set — it cannot tell you whether the user has
   actually completed the Gmail/Drive/Calendar OAuth flow for their
   account. Confirming that needs either a live Composio API call in that
   endpoint, or the user completing the connection UI and someone checking
   Composio's dashboard directly.
4. **Finish auth hardening if the in-flight agent didn't complete it** —
   check `git log` first (see the note under "Auth" above). If still open:
   token expiry, rate limiting on failed auth attempts, an audit trail of
   token use beyond `last_used_at`.
5. **Expand `jobos/api/main.py` test coverage** to the older endpoints
   listed above (stats, jobs, comp, content, profile, security/status,
   career-graph/summary, warmpath/races, shadow-mode, onboarding/wizard) —
   the pattern from `tests/integration/test_api_execute_action.py` /
   `test_generate_resume_endpoint.py` / `test_linkedin_upload_endpoint.py`
   is established and easy to repeat per-endpoint.
6. **Re-add the dashboard's top metrics strip somewhere**, or decide
   deliberately not to. The new workflow-sidebar dashboard (see above)
   dropped the Jobs Tracked / Applications Sent / Interviews Scheduled /
   RLS Rules stat tiles — they had no natural home in the new 6-section IA
   and weren't in the approved spec, so they were cut rather than force-fit
   somewhere. Flagged to the user; no decision made yet as of this writing.
