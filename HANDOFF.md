# JOBOS — Handoff / Project State

**Last updated:** 2026-08-11, by Claude (session covering commits `78815b0` → `ce65019`)

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

**310 tests passing.** `python -m pytest tests/ -q` from repo root
(`.venv` must be active, see Environment below).

### What is real and working end-to-end

- **Job ingestion** — polls public Greenhouse/Lever/Ashby boards, no API key
  needed. Verified live: pulled 108 real postings from Postman's board.
- **Matching pipeline** — scores ingested jobs against a Career Graph using
  local embeddings (no key), writes real `matches` rows with score/EV/tier.
- **Warm-path race** — durable DB-backed 7-day state machine
  (`warm_path_races` table). Sources referrers from the operator's own
  LinkedIn connections (imported via `jobos import`), not a paid API.
- **Entailment gate** — real LLM verifier call (needs a Groq key to actually
  run; currently untested against a live model, only against mocks).
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

- **API has no authentication.** Tenant identity comes entirely from a
  client-supplied `X-Tenant-Id` header. There is no default anymore (that
  hole was closed), so a missing header now 422s — but anyone who *sends* a
  header, any header, acts as that tenant. **This must land before the API
  is ever exposed off `localhost`.** Nothing in this plan built it; it was
  deliberately deferred (see the design spec below for the reasoning) and
  then deprioritized further when the user asked to build the pipeline
  first. It is still not done.
- **No LLM path has been run against a real model.** Groq key exists
  (per user) but hasn't been wired into `.env` or exercised end-to-end. All
  LLM-dependent code (entailment, tailoring, sequence generation, resume
  parsing, interview prep) is unit-tested against mocked responses only.
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

1. **API authentication.** Nothing else here is safe to expose off
   localhost until this lands. Opaque bearer tokens hashed at rest was the
   direction discussed with the user (see spec doc's earlier draft, section
   was cut when scope changed to "make it run first").
2. **Real LinkedIn export + Groq key wiring.** Both exist per the user; get
   them into `.env` / imported via `jobos import`, then run `jobos run` for
   real and see what an actual personalized run produces.
3. **Test coverage for `jobos/api/main.py`.** Currently zero. It's the
   most-churned file in the repo and the one most recently caught silently
   fabricating data.
4. **Fix the 3 broken seed company board tokens** in
   `data/seed_companies.yaml`.
5. **Dashboard**: reconcile the remaining static "phase explainer" panels
   (Phase 1, 2, 4-15 tabs) — right now only Phase 0's stat tiles read real
   data; the rest are documentation-style placeholders with hardcoded sample
   calculations, not live views. Lower priority than the above.
