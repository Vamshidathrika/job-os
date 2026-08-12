# JOBOS — Handoff / Project State

**Last updated:** 2026-08-12, by Claude (session covering commits `78815b0` → `b880b68`)

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

**333 tests passing.** `python -m pytest tests/ -q` from repo root
(`.venv` must be active, see Environment below).

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
  state. No endpoint fabricates a fallback number anymore (this was a real
  bug fixed this session — see below).

### What is explicitly NOT implemented (raises `NotImplementedError`, on purpose)

- **Cold apply** (`jobos/cold_apply/executor.py`) — Playwright browser
  automation. Refuses rather than claiming a submission that never happened.
- **GCP KMS** (`jobos/vault/kms.py`) — AWS KMS is implemented; GCP raises.
  Shipping a silent stub here would mean tenant DEKs were never wrapped.
- **LinkedIn publishing** (`jobos/runner/handlers.py::publish_post`) — no
  Composio LinkedIn connection wired up yet.

### What is NOT done and is the biggest real gap

- ~~**API has no authentication.**~~ **Done** (`6515dea`). Tenant identity now
  comes from an opaque bearer token, hashed at rest in `api_tokens`.
  `X-Tenant-Id` is ignored outright. Mint with
  `jobos --user-id <uuid> token create --name browser`; the dashboard has a
  paste-once login screen. `/health` stays public.
  Remaining caveats: tokens never expire (revoke by name to kill one), and
  there is no rate limiting on the auth endpoint.
- ~~**No LLM path has been run against a real model.**~~ **Code-level fix
  done** (`b880b68`) — key wiring was the actual bug (see above), verified
  down to a real rejected call from Groq's live API. Still blocked on the
  user's real key landing in `.env`; nobody has typed a real key value
  into this repo. All LLM-dependent code remains unit-tested against
  mocked responses only until that happens.
- **No real LinkedIn export has been imported.** The importer
  (`jobos/onboarding/linkedin_import.py`) is built and tested against a
  synthetic fixture ZIP, but the user's real export hasn't landed yet.
- **`jobos/api/main.py` has zero test coverage.** It was rewritten twice by
  a concurrent session and once by me this session; none of those changes
  added tests. Every "real" claim above about the API was verified by manual
  `curl` + a browser screenshot, not by an automated test. This is a real
  gap — add integration tests for this file next time it's touched.
- **3 of 8 seed companies have wrong ATS board tokens**
  (`data/seed_companies.yaml`: Chargebee, Zoho, Swiggy all 404 against their
  listed `ats_identifier`). The ingestion worker degrades correctly (skips
  the failure, continues the cycle) but those 3 companies currently
  contribute zero jobs. Fix by finding the correct board slug for each.

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
2. **Google Drive + broader Google-account scope — user asked for this,
   not yet built, needs a scoping decision first.** User wants: resumes
   generated and saved to their Google Drive, applications sent from their
   own Gmail, and "excellent at applying jobs and setting interviews"
   end-to-end. What exists: Gmail send (Composio, guarded by suppression +
   daily cap + shadow mode), Calendar client (`jobos/integrations/calendar.py`).
   What doesn't: Drive integration at all, and — the one that needs a real
   decision, not just code — autonomous job *submission*. Cold apply
   (`jobos/cold_apply/executor.py`) is deliberately unimplemented; building
   it means Playwright driving real ATS forms on real employer sites, which
   is both the highest-risk unverified action in this codebase (many ATS
   platforms fingerprint and ban bot-submitted applications — doing this
   wrong could hurt the user's actual applications) and something the user
   must explicitly choose the risk posture for (autonomous vs.
   review-then-approve, which is what shadow mode already defaults every
   other outbound action to). Do not build unattended auto-submit without
   that conversation happening first.
   Also: "read the user's LinkedIn connections live" is not the same ask as
   already-built — the importer reads LinkedIn's own data *export* (a file
   the user downloads themselves); there is no live LinkedIn API path that
   can read a profile or connections, and building a scraper is explicitly
   out of scope (account-ban risk, ToS violation) — this was already
   explained to the user earlier in this session and holds.
3. **Fix the 3 broken seed company board tokens** in
   `data/seed_companies.yaml` (Chargebee, Zoho, Swiggy all 404).
4. **Dashboard**: reconcile the remaining static "phase explainer" panels
   (Phase 1, 2, 4-15 tabs) — right now only Phase 0's stat tiles read real
   data; the rest are documentation-style placeholders with hardcoded sample
   calculations, not live views.
5. **Auth hardening** (the basics are done, these are the follow-ups):
   token expiry, rate limiting on failed auth, and an audit trail of token
   use beyond `last_used_at`.
