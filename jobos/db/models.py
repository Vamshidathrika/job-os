"""SQL schema definitions for JOBOS database tables."""

# Dimension of the job embedding vector. MUST match the output width of the
# configured LLMSettings.embedding_model — the default
# 'cloudflare/@cf/baai/bge-base-en-v1.5' emits 768 floats. Changing the model
# to one with a different width requires a migration that ALTERs this column.
EMBEDDING_DIM = 768

# Global Tables (no RLS)
COMPANIES_DDL = """
CREATE TABLE IF NOT EXISTS companies (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    domain text UNIQUE NOT NULL,
    canonical_name text,
    ats_type text,
    ats_identifier text,
    created_at timestamptz DEFAULT now()
);
"""

JOBS_DDL = f"""
CREATE TABLE IF NOT EXISTS jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
    external_id text NOT NULL,
    title text NOT NULL,
    location text,
    country text DEFAULT 'IN',
    description text,
    ats_type text,
    embedding vector({EMBEDDING_DIM}),
    raw_json jsonb,
    first_seen_at timestamptz DEFAULT now(),
    UNIQUE(company_id, external_id)
);
"""

JOB_REQUIREMENTS_DDL = """
CREATE TABLE IF NOT EXISTS job_requirements (
    job_id uuid PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    hard_reqs jsonb,
    preferred_reqs jsonb,
    min_yoe int,
    predicted_comp_p25 int,
    predicted_comp_p50 int,
    predicted_comp_p75 int
);
"""

SUPPRESSION_LIST_DDL = """
CREATE TABLE IF NOT EXISTS suppression_list (
    email_hash text PRIMARY KEY,
    reason text NOT NULL,
    created_at timestamptz DEFAULT now()
);
"""

# Tenant-isolated Tables (RLS enforced)
USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY,
    email text UNIQUE NOT NULL,
    linkedin_author_urn text,
    created_at timestamptz DEFAULT now()
);
"""

TENANTS_DDL = """
CREATE TABLE IF NOT EXISTS tenants (
    id uuid PRIMARY KEY,
    user_id uuid UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    plan text DEFAULT 'byok',
    autonomy_mode text DEFAULT 'shadow',
    onboarding_stage int DEFAULT 0,
    domain_warmup_started_at timestamptz,
    domain_warmup_complete boolean DEFAULT false,
    breaker_tripped_at timestamptz,
    breaker_reason text,
    created_at timestamptz DEFAULT now()
);
"""

TENANT_KEYS_DDL = """
CREATE TABLE IF NOT EXISTS tenant_keys (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    wrapped_dek bytea NOT NULL,
    kms_key_id text NOT NULL,
    rotated_at timestamptz DEFAULT now()
);
"""

CREDENTIALS_DDL = """
CREATE TABLE IF NOT EXISTS credentials (
    id uuid PRIMARY KEY,
    tenant_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
    provider text NOT NULL,
    kind text,
    ciphertext bytea,
    nonce bytea,
    last4 text,
    status text DEFAULT 'unvalidated',
    validated_at timestamptz,
    last_error text,
    UNIQUE(tenant_id, provider)
);
"""

CG_BULLETS_DDL = """
CREATE TABLE IF NOT EXISTS cg_bullets (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    company text,
    role text,
    bullet_text text,
    metric text,
    evidence_url text,
    verification_status text DEFAULT 'unverified',
    retrieval_count int DEFAULT 0,
    created_at timestamptz DEFAULT now()
);
"""

MATCHES_DDL = """
CREATE TABLE IF NOT EXISTS matches (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    job_id uuid REFERENCES jobs(id) ON DELETE CASCADE,
    score float,
    ev_score float,
    tier int,
    status text DEFAULT 'matched',
    created_at timestamptz DEFAULT now(),
    UNIQUE(user_id, job_id)
);
"""

APPLICATIONS_DDL = """
CREATE TABLE IF NOT EXISTS applications (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    job_id uuid REFERENCES jobs(id) ON DELETE CASCADE,
    path text,
    band text,
    tailored_resume_url text,
    submitted_at timestamptz,
    status text DEFAULT 'pending',
    created_at timestamptz DEFAULT now()
);
"""

PEOPLE_DDL = """
CREATE TABLE IF NOT EXISTS people (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    company_domain text,
    full_name text,
    title text,
    email text,
    email_verified boolean DEFAULT false,
    linkedin_url text,
    tenure_years float,
    shared_context jsonb,
    created_at timestamptz DEFAULT now()
);
"""

REFERRAL_SEQUENCES_DDL = """
CREATE TABLE IF NOT EXISTS referral_sequences (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    person_id uuid REFERENCES people(id) ON DELETE CASCADE,
    job_id uuid REFERENCES jobs(id) ON DELETE CASCADE,
    step int DEFAULT 1,
    status text DEFAULT 'active',
    t1_sent_at timestamptz,
    t2_sent_at timestamptz,
    t3_sent_at timestamptz,
    created_at timestamptz DEFAULT now()
);
"""

OUTBOX_DDL = """
CREATE TABLE IF NOT EXISTS outbox (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    channel text,
    payload jsonb,
    scheduled_for timestamptz,
    status text DEFAULT 'pending',
    error text,
    created_at timestamptz DEFAULT now()
);
"""

AGENT_DECISIONS_DDL = """
CREATE TABLE IF NOT EXISTS agent_decisions (
    id uuid PRIMARY KEY,
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    module text,
    action text,
    inputs jsonb,
    outputs jsonb,
    prompt_version text,
    created_at timestamptz DEFAULT now()
);
"""

TENANT_COMPANY_UNIVERSE_DDL = """
CREATE TABLE IF NOT EXISTS tenant_company_universe (
    tenant_id uuid REFERENCES tenants(id) ON DELETE CASCADE,
    company_id uuid REFERENCES companies(id) ON DELETE CASCADE,
    tier int DEFAULT 2,
    PRIMARY KEY(tenant_id, company_id)
);
"""

ALL_DDL = [
    COMPANIES_DDL,
    JOBS_DDL,
    JOB_REQUIREMENTS_DDL,
    SUPPRESSION_LIST_DDL,
    USERS_DDL,
    TENANTS_DDL,
    TENANT_KEYS_DDL,
    CREDENTIALS_DDL,
    CG_BULLETS_DDL,
    MATCHES_DDL,
    APPLICATIONS_DDL,
    PEOPLE_DDL,
    REFERRAL_SEQUENCES_DDL,
    OUTBOX_DDL,
    AGENT_DECISIONS_DDL,
    TENANT_COMPANY_UNIVERSE_DDL,
]
