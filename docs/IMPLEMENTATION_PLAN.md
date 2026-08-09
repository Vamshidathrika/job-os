# JOBOS — 16-Phase Implementation Plan
## *Subagent-Driven Parallel Development & Mandatory Verification Gates*

---

## 1. Master Build Roadmap (~74 Days)

| Phase | Module / Subsystem | Days | Core Deliverable |
|---|---|---|---|
| **0 & 0b** | Multi-Tenancy & Key Vault | 5 | RLS policies, KMS envelope encryption, credential scrubber, DB schema setup. |
| **1** | Global ATS Ingestion Engine | 4 | In-process `httpx` worker for ~800 ATS endpoints, normalization, pgvector embeddings. |
| **1b** | Hiring Radar | 2 | Passive signal detection (funding announcements, velocity spikes, exec departures). |
| **2–4** | Graph, Matcher & Tailorer | 10 | Career graph evidence engine, dual-family LLM entailment verifier, resume generator. |
| **5** | Compensation Intel & EV | 3 | Ashby/Adzuna/Levels comp model, EV calculation, defensive comp deflection policy. |
| **6 & 6b** | Referral Engine & Compliance | 5 | Apollo & Icypeas search, `score_referrer()`, 3-touch sequence, SHA-256 global suppression. |
| **6c** | Network Graph Mapper | 2 | Existing contact mapping prior to cold referral search. |
| **7** | Warm-Path 7-Day Race | 3 | Temporal workflow engine, 7-day TTL hold vs apply decision matrix. |
| **8** | Content & Seed Comment Engine | 2 | Official LinkedIn API (`w_member_social`), pillar content pipeline, comment engine ($35\%$ skip rate). |
| **9** | Profile Keyword Optimizer | 2 | TF-IDF target job corpus extraction, headline formula generator, search ranking tracking. |
| **10 & 10b** | Action Queue & Dashboard | 9 | Mobile connection request card UI, 10-panel command dashboard with `agent_decisions` drill-down. |
| **11** | Interview Prep & Debrief | 4 | Dossier generator, progressive push notifications, $+90\text{m}$ debrief loop compounding graph. |
| **12** | Fallback Apply Executor | 5 | Playwright auto-apply executor (Band A/B fallback channel). |
| **12b** | Post-Interview Follow-Up Engine | 2 | Auto thank-you email engine + status tracking & ghost detection. |
| **13** | Composio Gmail/Calendar | 2 | Gmail draft/send integration, Google Calendar idempotency with `jobos_key`. |
| **14 & 14b** | Circuit Breakers & Canaries | 7 | Per-tenant + global circuit breakers, staged prompt canary deploy pipeline ($5\% \rightarrow 25\% \rightarrow 100\%$). |
| **15** | Onboarding & Shadow Mode | 5 | Progressive activation ladder, 7-day shadow mode floor, instant profile value delivery. |

---

## 2. Subagent Architecture & Parallel Tracks

Development is organized across 6 specialized subagents working in parallel per phase:

1. **DB Architect (`db_architect`)**: PostgreSQL 16 schema, pgvector, Alembic migrations, RLS policies, `tenant_conn()` wrapper.
2. **Backend Engineer (`backend_engineer`)**: FastAPI endpoints, vault encryption, domain logic, policy assertions.
3. **Integration Engineer (`integration_engineer`)**: Composio SDK tools (Gmail, Calendar, LinkedIn, Apollo, Icypeas).
4. **Test Engineer (`test_engineer`)**: Mandatory test suites (unit, security, integration, e2e, golden sets).
5. **Frontend Engineer (`frontend_engineer`)**: Next.js 15 dashboard (10 panels) & Action Queue mobile PWA.
6. **DevOps Engineer (`devops_engineer`)**: Docker Compose, GitHub Actions CI/CD pipeline, staging deploys.

---

## 3. Mandatory Quality & Verification Gates

No phase advances to the next without passing all verification gates:

- **Type Check:** `pyright jobos/ --pythonversion 3.11` (0 errors)
- **Lint Check:** `ruff check jobos/ tests/` (0 errors)
- **Security Tests:** `pytest tests/security/ -v` (100% pass)
- **Unit & Integration Tests:** `pytest tests/unit/ tests/integration/ -v` (100% pass)
- **Entailment Golden Set:** $\ge 95\%$ accuracy on 30 benchmark entailment pairs before tailorer deploys.

---

## 4. Founder Decision Gates

- **Day 22 (Gate 1):** IP Validation — Does the matcher & tailorer operate without fabrication?
- **Day 39 (Gate 2):** Channel Validation — Do referral sequences achieve $\ge 35\%$ reply rate?
- **Day 48 (Gate 3):** Product Validation — Is the 10-panel dashboard readable in 60 seconds?
- **Day 74 (Gate 4):** Beta Launch — Can a new tenant reach a tailored resume in $< 30$ seconds?
