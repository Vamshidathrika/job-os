# JOBOS — Master Architecture Specification
## v3.1 Architecture & Technical Blueprint

---

## 1. Executive Topology & Data Flow

```
                                GLOBAL INGESTION WORKER (Single Process) 
                        ~800 Target Companies via `httpx` (Unauthenticated GETs)
                                                  │
                                                  ▼
                               Global Normalization, Vector Embeddings
                                    & Job Requirements Extraction
                                                  │
                                                  ▼
                        PER-TENANT WORKFLOW ENGINE (Postgres RLS Isolation)
                     Triggered on `job.new` for each Interested Tenant (Tenant DEK Active)
                                                  │
                                         Is Role High-Value?
                                       ┌──────────┴──────────┐
                                      YES                    NO
                                       │                     │
                                       ▼                     ▼
                           7-DAY WARM PATH RACE       BAND A COLD APPLY
                         (Temporal Workflow Engine) (Playwright Auto-Executor)
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 ▼                     ▼                     ▼
          REFERRAL PATH         RECRUITER PATH         SIGNAL PATH
          2-Touch Email         1-Touch Direct         Official API
          (Gmail Draft/Send)    Req Pitch              LinkedIn Posts & Seed
                 │                     │               Comments via Composio
                 └─────────────────────┼─────────────────────┘
                                       │
                            Any Warm Path Responded?
                           ┌───────────┴───────────┐
                          YES                      NO (after 7 days)
                           │                       │
                           ▼                       ▼
                Apply with Referral          Fallback to Cold Apply
```

---

## 2. Key Subsystem Integrations & Security Mechanics

### 2.1 Database Isolation vs Shared Ingestion
* **Shared Global Tables (Read-Only to Tenants):** `companies`, `jobs`, `job_requirements`. Deduped global polling across all tenant target company lists (`tenant_company_universe`).
* **Tenant-Isolated Tables (Postgres RLS Enforced):** `applications`, `cg_bullets`, `people`, `evidence_items`, `referral_sequences`, `outbox`, `agent_decisions`, `credentials`, `tenant_keys`.
* **RLS Enforcement:** `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` on every tenant table. Connection checkout uses `BEGIN` + `SELECT set_config('jobos.tenant_id', $1, true)`.
* **Never Shared Data:** `people` and `evidence_items` remain strictly isolated to one tenant.

### 2.2 Vault & Envelope Encryption
* **Master KMS Key** (AWS KMS / GCP KMS / Local Dev KMS) wraps per-tenant DEK stored in `tenant_keys`.
* **Credentials:** API keys/OAuth tokens encrypted with AES-256-GCM using per-credential nonces.
* **Redaction Boundary:** Structlog allowlist processor scrubs credentials from all log outputs, Sentry, and `agent_decisions.inputs`.
* **Tenant Deletion Protocol:** Dropping a tenant drops the DEK, rendering data unrecoverable instantly (GDPR Art. 17 & DPDP Act 2023 §12).

### 2.3 Cross-Family LLM Entailment & Anti-Fabrication Gate
* **Dual-Model Requirement:** Tailoring LLM (OpenRouter / Groq) and Entailment Verifier LLM (NVIDIA NIM) MUST belong to different model families.
* **Single-Key Fallback:** If tenant provides only 1 LLM key or both resolve to the same family, autonomous tailoring is refused $\rightarrow$ locked to **Band C (Queue-Only)**.
* **Factual Grounding:** Every bullet point in a tailored resume or referral email maps 1-to-1 to a verified evidence item URL.

### 2.4 Composio Edge & Tool Defensive Rules
* **Degradation Shield (`composio_call`):** Composio outage degrades calendar and outreach into paused state without halting ingestion, matching, or tailoring.
* **Verified Tool Defenses:**
  * `LINKEDIN_GET_MY_INFO`: Fetched once per user, mapped to `urn:li:person:<subnum>`, cached permanently in DB.
  * `GOOGLECALENDAR_CREATE_EVENT`: Idempotency checked via `GOOGLECALENDAR_EVENTS_LIST` using `privateExtendedProperty` (`jobos_key=jobos_iv_<id>`). Durations $>59\text{m}$ mapped to `event_duration_hour`; timezones enforced as IANA strings (`Asia/Kolkata`).
  * `LINKEDIN_CREATE_LINKED_IN_POST`: Validates presence of `x_restli_id` / `id` (catches silent 200s). Traps 422 `DUPLICATE_POST` as generator repetition.
  * `GMAIL_FETCH_EMAILS`: 3-minute query polling replacing `users.watch`. Client-side sort by `internalDate`.

### 2.5 The 7-Day Warm-Path Race Engine
* **High-Value Trigger:** Matched score $\ge 0.65$ & high EV triggers 7-day Temporal workflow.
* **Multi-Channel Orchestration:**
  1. **Referral Engine:** Apollo (identity) + Icypeas (`school`, `pastCompanyName`) $\rightarrow$ scored via `score_referrer()` $\rightarrow$ 3-touch sequence via Gmail. Personalization gate drops low-tier slop ($40\text{--}60\%$ target drop rate).
  2. **Recruiter Direct Pitch:** Sourced recruiter $\rightarrow$ 1-touch direct value pitch with tailored resume.
  3. **Signal & Behavioral Cover:** Composio LinkedIn (`w_member_social`) daily posts ($40\%$ proof-of-work) $+ 6\text{--}12$ seed comments/day ($35\%$ skip rate).
  4. **Action Queue:** Mobile card stack serving pre-researched connection requests ($\le 20/\text{day}$, $\ge 30\%$ acceptance floor).
* **Race Resolution:** Reply received $\rightarrow$ apply with referral. 7 days elapse $\rightarrow$ Playwright cold apply fallback.

### 2.6 Compensation Intelligence & EV Ranking
* **EV Formula:** $\text{EV} = P(\text{offer} \mid \text{profile}) \times \text{predicted\_comp} \times P(\text{accept})$.
* **Defensive Comp Policy:** Current CTC $\rightarrow$ Mandatory human escalation (Band C). Numeric required $\rightarrow$ Auto-fill $75^{\text{th}}$ percentile of predicted band. Text $\rightarrow$ Strategic market deflection statement.

### 2.7 Post-Interview Debrief Loop
* **Dossier Generation:** Auto-generates Markdown/PDF dossier containing *The Bet*, *Requirement $\rightarrow$ Verified Evidence Mapping*, *Gap Defense Bridges*, *12–18 STAR Questions*, *Interviewer Dossier*, *Company Intel*, and *3 Tailored Questions*.
* **Progressive Push:** Calendar link $\rightarrow$ T-24h Top 5 questions push $\rightarrow$ T-2h 3-line summary push.
* **Debrief Loop (+90 min Post-Interview):** Prompts candidate with 3 debrief questions $\rightarrow$ extracts new STAR bullets into `cg_bullets` $\rightarrow$ auto-tunes company question predictor.

### 2.8 Safety & Circuit Breakers
* **Circuit Breakers:** Per-tenant limits + Global Breakers (trips if global entailment failure $>15\%$, outbox failure $>25\%$, or personalization gate floor $<15\%$).
* **Staged Canary Deploys:** Prompt changes git-versioned, rolled out via canary ($5\% \rightarrow 25\% \rightarrow 100\%$) with auto-rollback.
* **Global Suppression List:** SHA-256 email hashes checked before *every* outbound send across all tenants without exception.
