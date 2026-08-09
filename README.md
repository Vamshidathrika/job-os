# 🚀 JOBOS — Autonomous Warm-Path Job Search Engine
### *Multi-Tenant · Bring Your Own Key (BYOK) · Envelope Encrypted · RLS Isolated*

[![CI Status](https://github.com/Vamshidathrika/job-os/actions/workflows/ci.yml/badge.svg)](https://github.com/Vamshidathrika/job-os/actions)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-blue)](https://www.postgresql.org/)
[![Security](https://img.shields.io/badge/Isolation-Postgres%20RLS-success)](file:///Users/nani/Downloads/primeneuro/jobos/docs/ARCHITECTURE.md)

---

## 🎯 The Core Thesis

**Cold application destroys optionality.** Cold applications convert at ~3% to interviews, creating duplicate records in ATS portals that discount subsequent referrals.

**JOBOS inverts the funnel:** One real referral yields a **~40% interview rate** (1 referral ≈ 40 cold applications).

> **JOBOS is an autonomous machine that manufactures warm paths into companies you target at volume, only falling back to cold applying when the 7-day warm-path race fails.**

```
                     JOB INGESTION & PIPELINE (Global In-Process Worker)
                     ~800 Target Companies via `httpx` (unauthenticated GETs)
                                              │
                                              ▼
                             Jobs Normalization & Vector Embeddings
                                              │
                                              ▼
                     PER-TENANT WORKFLOW ENGINE (Postgres RLS Isolated per Tenant)
                                              │
                                    Is Job High-Value?
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

## 🔥 Key System Superpowers

1. **7-Day Warm-Path Race:** Holds cold applications for high-value Tier-1/2 roles while executing a 3-touch referral sequence via Apollo + Icypeas + Gmail API.
2. **Postgres RLS Tenant Isolation:** Row-Level Security (`FORCE ROW LEVEL SECURITY`) on all tenant tables with transaction-scoped `SET LOCAL jobos.tenant_id`.
3. **KMS Envelope Encryption:** AWS/GCP KMS Master Key wraps per-tenant DEK. Credentials encrypted with AES-256-GCM. Log scrubber enforces zero plaintext keys in logs/Sentry.
4. **Dual-Model Entailment Verifier:** Requires distinct LLM model families for tailoring vs verification. Fabrication is mathematically impossible — every bullet point maps 1-to-1 to a verified evidence item URL.
5. **Expected Value (EV) Ranking:** $\text{EV} = P(\text{offer}) \times \text{predicted\_comp} \times P(\text{accept})$. Ranks opportunities by expected monetary return. Defensive policy deflects salary anchoring.
6. **Official API Behavioral Cover:** Autonomous posting ($40\%$ proof-of-work) and seed commenting ($6\text{--}12/\text{day}$) via Composio LinkedIn official API (`w_member_social`). Anti-slop contract ensures Hinglish/Telglish operator voice.
7. **90-Second Mobile Action Queue:** Connection requests are pre-researched, pre-drafted, and delivered as mobile card stacks. Governed by a $\ge 30\%$ acceptance rate floor. Zero illegal browser automation.
8. **Compounding Prep Dossier & Debrief Loop:** Auto-generates dossier with STAR answers $+90\text{ min}$ post-interview debrief loop that appends new STAR stories back to the candidate's Career Graph.

---

## 🛠️ Tech Stack & Architecture

- **Backend:** Python 3.11+ / FastAPI / Pydantic v2 / Structlog
- **Database:** PostgreSQL 16 + pgvector (Asyncpg, Alembic migrations, RLS policies)
- **Task Orchestration:** Temporal Python SDK (durable 7-day workflows)
- **Integrations:** Composio SDK (Gmail, Google Calendar, LinkedIn, Apollo, Icypeas)
- **LLM Routing:** LiteLLM (Groq, OpenRouter, NVIDIA NIM)
- **Browser Automation:** Playwright (stealth headful fallback cold apply)
- **Frontend / Mobile UI:** Next.js 15 + React / Installable PWA Action Queue

---

## 🔒 Multi-Tenant Safety & Compliance Rules

- **RLS Mandatory:** `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` on all tenant tables.
- **Global Suppression List:** SHA-256 hashed emails checked cross-tenant prior to *every* outbound send.
- **GDPR Art. 14 & DPDP Act 2023:** Automatic data-source disclosure footers on first contact with prospects.
- **Circuit Breakers:** Global breakers trip on global entailment failure $>15\%$, outbox failure $>25\%$, or tier-gate rejection floor $<15\%$.
- **7-Day Shadow Mode Floor:** All new tenants start in shadow mode (simulated execution) for 7 days.

---

## ⚡ Quick Start (Local Development)

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.11+

### 2. Setup Environment
```bash
git clone https://github.com/Vamshidathrika/job-os.git
cd job-os
cp .env.example .env
```

### 3. Start Infrastructure
```bash
docker-compose up -d
```
Starts PostgreSQL + pgvector (port 5432), Test DB (port 5433), Temporal (port 7233), and Temporal UI (http://localhost:8080).

### 4. Install & Run Tests
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run test suites
pytest tests/security/ -v  # RLS & credential isolation tests
pytest tests/unit/ -v      # Unit tests
```

---

## 📚 Documentation

- [Master Architecture Specification](docs/ARCHITECTURE.md)
- [16-Phase Implementation Plan](docs/IMPLEMENTATION_PLAN.md)
- [Brainstorm & Loophole Analysis](docs/BRAINSTORM.md)

---

## 📜 License

MIT License © 2026 Vamshi Dathrika. All rights reserved.
