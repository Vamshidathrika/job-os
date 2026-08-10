# First Real Run — Design

**Date:** 2026-08-10
**Status:** Approved
**Scope:** Make JOBOS execute end to end on one operator's real data, using only free-tier credentials.

## Problem

JOBOS is a parts bin, not a machine. Every engine is implemented and tested, and
almost none of it is reachable. Non-definition call sites inside `jobos/`:

| Engine | Callers |
|---|---|
| `GlobalIngestionWorker` | 0 |
| `find_referrers` | 0 |
| `send_email_guarded` | 0 |
| `verify_entailment` | 0 |
| `generate_tailored_resume` | 0 |
| `classify_tier` / `calculate_ev` / `should_hold_application` | 0 |
| `ActionExecutor` | 0 |
| `process_signals` | 0 |

There is no `__main__`, no `[project.scripts]`, no CLI and no scheduler. The
Dockerfile runs `uvicorn jobos.api:app` only, so the sole runnable artefact is
an API serving dashboard reads. Nothing ingests, matches, races or sends.

Nothing seeds the `companies` table either, so even a wired-up ingestion worker
would poll an empty universe.

## Goals

1. One command runs the full pipeline against real data.
2. Everything is personalised from the operator's actual career history.
3. It works on free-tier credentials only (Groq + Composio), plus no-key job ingestion.
4. No outbound message reaches a human without explicit approval.

## Non-goals

Deliberately excluded from this build:

- **Cold apply** (Playwright ATS automation) — currently raises `NotImplementedError`
  by design; it is the race's fallback and only matters once the race can expire.
- **Apollo / Icypeas stranger-sourcing** — paid. Warm paths come from the
  operator's existing connections instead.
- **API authentication** — the API trusts a client-supplied `X-Tenant-Id`
  header, which is a full tenant-impersonation hole. It is out of scope only
  because the system runs locally and does nothing yet. **This must land before
  the API is exposed to any network.** Tracked as the immediate next project.

## Key decisions

### LinkedIn data comes from the operator's own export, never from scraping

Scraping profiles violates LinkedIn's terms and risks permanent account loss.
The official API scope in use (`w_member_social`) is post-only and cannot read
profile data; Sign In with LinkedIn returns only name, email and photo.

The legitimate source is the operator's own data export (Settings → Data
Privacy → Get a copy of your data), which contains `Positions.csv`,
`Education.csv`, `Skills.csv` and `Connections.csv`. This is higher fidelity
than scraping would produce, and it is the operator's own data.

### Warm paths come from `Connections.csv`

`Connections.csv` lists every person the operator knows, with company. Fed to
the existing `map_existing_network`, this produces referrer candidates with
genuine shared history and **no paid API**. Apollo would only add strangers.

Consequence to accept: if the operator's connections do not overlap their
target companies, the race finds nobody and every job falls through to "no warm
path available". This is a real possible outcome and is visible within minutes
of import.

### Embeddings run locally

`LLMSettings.embedding_model` currently points at Cloudflare Workers AI, which
needs another account and quota. Switching to a local ONNX model (`fastembed`,
bge-small-en-v1.5, 384 dims) removes a credential, a network dependency and a
rate limit from the matching path. `EMBEDDING_DIM` moves 768 → 384 with a
migration altering `jobs.embedding`.

Cloudflare remains selectable via settings for anyone who wants it.

### Shadow mode is the default, and the send path is the only way out

Tenants start in shadow mode (already the schema default). Every outbound
message is queued to Band B for human approval. The suppression list and the
daily cap sit inside `send_email_guarded`, which is the only sanctioned way to
send — a control callers can bypass is not a control.

## Architecture

Six components, each independently testable.

### 1. Profile importer — `jobos/onboarding/linkedin_import.py`

Reads a LinkedIn export ZIP and an optional résumé; merges into the Career
Graph.

- Parses `Positions.csv`, `Education.csv`, `Skills.csv`, `Connections.csv`.
- Merges with `parse_uploaded_resume` output. On conflict the LinkedIn export
  wins (structured data beats parsed text).
- Writes `cg_bullets` as `unverified` — imported history is claimed, not
  verified, and the tailorer may only use verified bullets.
- Writes connections to `people`. That table has no provenance column today, so
  this adds `people.source text` via migration; connections import as
  `'linkedin_connection'`.

Depends on: `cg_bullets`, `people`, `parse_uploaded_resume`.

### 2. Company universe seeding — `jobos/ingestion/seed_companies.py`

Ships a curated seed list (`data/seed_companies.yaml`) of companies with their
ATS type and board identifier, and upserts it into `companies`. Editable by the
operator. Without this the ingestion worker polls nothing.

### 3. Matching pipeline — `jobos/matcher/pipeline.py`

The missing glue between ingestion and the race:

```
jobs (embedded) + profile embedding
  → compute_similarity            (scorer.py, exists)
  → compute_requirement_match     (scorer.py, exists)
  → predict_salary_band           (comp/predictor.py, exists)
  → calculate_ev                  (ev_ranker.py, exists)
  → classify_tier                 (tier_gate.py, exists)
  → write matches rows
```

All five callees already exist and are tested. This component only sequences
them and persists the result.

### 4. Orchestrator — `jobos/runner/pipeline.py` + `jobos/cli.py`

A new `jobos/runner/` package rather than an addition to `jobos/workers/`:
`workers/` holds units of work that do one job (the ingestion worker), while
`runner/` sequences them and owns the process lifecycle. Keeping the caller out
of the callee's package is what stops the orchestrator becoming a god module.

One command, explicit stages, each independently runnable:

| Command | Action |
|---|---|
| `jobos import` | Profile importer |
| `jobos seed` | Company universe |
| `jobos ingest` | `GlobalIngestionWorker.run_cycle()` |
| `jobos match` | Matching pipeline |
| `jobos race` | Start races for Tier-1; resolve expired ones |
| `jobos work` | Drain due actions via `ActionExecutor` |
| `jobos run` | All of the above, in order |

Registered as `[project.scripts] jobos = "jobos.cli:main"`.

Each stage returns counts and is idempotent, so a re-run repairs rather than
duplicates.

### 5. Action handlers — `jobos/runner/handlers.py`

`ActionExecutor` dispatches by `action_type`; nothing currently registers
handlers. This registers them:

- `referral_touch` → `send_email_guarded` (suppression + cap enforced)
- `submit_application` → refuses, pending cold apply
- `publish_post` → refuses, pending LinkedIn posting

### 6. Race wiring

`should_hold_application(tier == 1)` decides hold vs queue. For a held job:

1. `map_existing_network(connections, [company_domain])` returns the operator's
   own connections at that company. This replaces `find_referrers` for this
   build — `find_referrers` needs Apollo and stays unused until a key exists.
2. The highest-scoring candidate goes to `generate_referral_sequence`, which
   drops anyone lacking real shared context (the personalisation gate).
3. `WarmPathRace.start_race(touches=sequence)` schedules the touches across the
   week.

Expired races surface through `find_expired_races` and are resolved. A job with
no connections at the company gets no race and is recorded as
`no_warm_path_available` rather than silently skipped.

## Data flow

```
LinkedIn export ZIP + résumé
        │
        ▼
   Career Graph (cg_bullets, people)
        │
        ├── profile embedding ─────────┐
        │                              ▼
seed_companies → ingest (public ATS) → jobs (embedded)
                                       │
                                       ▼
                              matching pipeline → matches (score, ev, tier)
                                       │
                              tier == 1 ?
                          ┌────────────┴────────────┐
                         yes                        no
                          ▼                         ▼
              warm path race (7d)            queued, no action
                          │
        connections ∩ target company
                          ▼
              Groq drafts sequence
                          ▼
              queued Band B (shadow mode)
                          ▼
                 operator approves
                          ▼
              send_email_guarded → Gmail
```

## Error handling

Follows the conventions already established in this codebase:

- **Fail closed on anything reaching a human.** Entailment, suppression and cap
  failures block the send. No verdict never means "approved".
- **Degrade, don't abort, on ingestion.** One unreachable board returns an empty
  list; the cycle continues. Counters distinguish "nothing to do" from "all
  failed", and a cycle where everything failed logs at error level.
- **Never fabricate.** Missing data yields empty fields, not invented ones.
- **Idempotent stages.** Every write is an upsert keyed on a natural key, so
  re-running a stage is safe.

## Testing

- **Unit** — importer parsing (fixture LinkedIn export ZIP), pipeline scoring,
  handler dispatch. LLM and HTTP mocked.
- **Integration, against real Postgres** — importer → Career Graph; matching
  pipeline → `matches`; race start/resolve; handler → guarded send. Tenant
  isolation asserted on every new table access.
- **End-to-end smoke** — seeded companies + stubbed ATS payloads + stubbed LLM,
  running `jobos run` and asserting rows land in `jobs`, `matches`,
  `warm_path_races` and `action_queue`.

Existing suite is 275 passing and must stay green.

## Risks

| Risk | Mitigation |
|---|---|
| Operator's connections don't overlap target companies | Visible immediately post-import; report the overlap count during `jobos import` |
| Groq free-tier rate limits during bulk tailoring | Tailor lazily — only for Tier-1 jobs, only when the race starts |
| `fastembed` model download on first run | Document it; ~50MB, one time |
| LinkedIn changes its export CSV headers | Importer validates expected columns and fails loudly with the mismatch |
| Accidental real send during development | Shadow mode default on; suppression + caps in `send_email_guarded`; no autonomous band until explicitly enabled |
