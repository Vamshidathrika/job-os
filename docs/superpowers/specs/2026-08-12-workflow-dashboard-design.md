# Workflow-oriented dashboard redesign

Date: 2026-08-12
Status: approved, ready for implementation plan

## Problem

The current dashboard (`dashboard/src/App.tsx`) exposes 15 tabs named after
internal backend modules ("Phase 0: Security & Vault", "Phase 3: Matcher &
EV Ranker", ...). This maps to how the engine is implemented, not to how a
candidate actually works a job search. User feedback: "too poor hard to
understand and what are that 15 buttons why i will click them."

The user's actual requirement, restated: connect LinkedIn (via data export
— live LinkedIn login/scraping is not possible and risks account ban, this
was already established and is not being revisited), search jobs from
multiple sources, get a tailored resume per job, get interview-prep notes,
get referrals for the target company, and use Composio to send email,
store resumes in Drive, and block calendar time for interviews.

## Navigation

Sidebar replaces the phase grid. Six sections, in workflow order:

1. **Profile & LinkedIn** — one-time upload of the LinkedIn data export
   zip; re-upload anytime from this page. Shows the parsed career graph
   summary (skills, roles, comp bands) once imported.
2. **Job Matches** — jobs list with tier (1/2/3) and EV score, filterable.
   Clicking a job opens a detail view with a "Generate tailored resume"
   action that runs the real tailoring pipeline and returns a Drive link.
3. **Applications** — the cold-apply review queue (today's Phase 12
   content, relocated as-is) plus a status tracker per job.
4. **Referrals** — warm-path race status and referral sequences (today's
   Phase 6/6c/7 content, relocated).
5. **Interview Prep** — prep notes and debrief content once an interview
   exists; honest "not wired yet" state where the backend is still a stub
   (entailment scoring).
6. **Calendar & Integrations** — Composio connection status for
   Gmail/Drive/Calendar, calendar auto-block behavior, and an "Advanced"
   collapsible panel holding the security/RLS/vault status that used to be
   Phase 0.

**Global header:** a "Needs your review" bell with a count, listing every
pending action across all types and bands in one inbox — not scattered
per-section. Every send/apply/schedule action still requires explicit
human approval before it executes (standing decision from earlier in this
project; not being revisited here). Shadow-mode pill and sign-out stay in
the header.

## Components (frontend)

- `Sidebar` — 6 nav items, replaces the phase-tab grid.
- `TopBar` — logo, review-inbox bell + count, shadow-mode pill, sign out.
- `ReviewInboxPage` — lists all `action_queue` rows with `status='pending'`
  across bands/types. Approve calls the existing
  `POST /api/actions/{id}/execute`. Reject calls a new
  `POST /api/actions/{id}/reject`.
- `ProfilePage` — upload zone for the LinkedIn export zip, calls a new
  upload endpoint (see below); shows career-graph summary via the existing
  `GET /api/career-graph/summary`.
- `JobMatchesPage` — reuses existing `jobs` data already fetched by the
  dashboard; adds a job detail drawer with a "Generate tailored resume"
  button wired to the existing resume pipeline stage
  (`jobos/runner/pipeline.py::stage_upload_resume`), surfaced through a
  new thin API endpoint (see below).
- `ApplicationsPage` — today's Phase 12 JSX, moved, not rewritten.
- `ReferralsPage` — today's Phase 6/6c/7 JSX, moved, not rewritten.
- `InterviewPrepPage` — today's Phase 4/11 JSX, moved, not rewritten.
- `CalendarIntegrationsPage` — today's Phase 13/14 JSX plus the security
  panel from Phase 0, moved under "Advanced".

## Backend — new endpoints

Three additions; everything else reuses endpoints already built this
session.

1. `GET /api/actions?status=pending` — cross-band, cross-type list for the
   review inbox. Today's `GET /api/actions?band=` only splits by band and
   is kept for the relocated per-section pages.
2. `POST /api/actions/{id}/reject` — marks an action `status='rejected'`
   without running its handler. Symmetric with the existing
   `mark_complete`/`mark_failed` methods on `ActionQueue`; add
   `mark_rejected`.
3. `POST /api/onboarding/linkedin-import` — accepts an uploaded LinkedIn
   export zip (multipart), runs the existing import logic that today is
   CLI-only, returns the parsed profile summary. Scope: reuse the existing
   parser/importer module directly; this endpoint is a thin HTTP wrapper,
   not new parsing logic.
4. `POST /api/jobs/{id}/generate-resume` — thin wrapper calling
   `stage_upload_resume` for the given job and the authenticated tenant's
   user, returning the Drive file link. (Counted as the 4th endpoint but
   grouped with #3 as "wrap an existing pipeline stage in HTTP", not new
   business logic.)

## Data flow

No changes to matching, tailoring, referral, or cold-apply logic. This is
an IA reorg on the frontend plus thin HTTP wrappers around pipeline stages
that currently only run via CLI. RLS/tenant auth on new endpoints follows
the exact pattern already used by every other route in `jobos/api/main.py`
(`Depends(authenticated_tenant)`, `Depends(tenant_db)`).

## Error handling

Keep the honest-empty-state pattern established in this session's earlier
dashboard fix: no fabricated fallback numbers, no fake "CONNECTED"
defaults. Apply it to every new/relocated page. A stub backend (e.g.
entailment scoring) says so in the UI instead of showing fake data.

## Testing

- Backend: pytest integration tests for the 3 new endpoints
  (`mark_rejected`, LinkedIn upload wrapper, resume-generate wrapper),
  following the existing pattern in `tests/integration/test_api_execute_action.py`.
- Frontend: no test framework is currently wired into `dashboard/`; manual
  browser verification via the existing `mcp__Claude_Browser__*` workflow
  stays the verification method for this round, consistent with how the
  rest of the dashboard was verified this session.

## Scope for this round (MVP, per explicit approval)

Build fully real: sidebar shell + routing, review inbox (approve/reject),
Job Matches page with end-to-end resume generation.

Relocate without rewriting: Applications, Referrals, Interview Prep,
Calendar & Integrations pages — move existing JSX into the new IA,
apply the honest-empty-state pattern, no new backend work on these this
round.
