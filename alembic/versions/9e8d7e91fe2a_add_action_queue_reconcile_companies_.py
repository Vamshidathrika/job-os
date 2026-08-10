"""add action_queue, reconcile companies and tenant_company_universe

Revision ID: 9e8d7e91fe2a
Revises: 7ab0f93b11ea
Create Date: 2026-08-10 10:05:46.459103

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.models import ACTION_QUEUE_DDL, ACTION_QUEUE_INDEX_DDL
from jobos.db.rls import generate_rls_sql


# revision identifiers, used by Alembic.
revision: str = '9e8d7e91fe2a'
down_revision: Union[str, None] = '7ab0f93b11ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # companies: id had no default and updated_at (written by hiring_radar)
    # never existed, so every radar upsert failed.
    op.execute("ALTER TABLE companies ALTER COLUMN id SET DEFAULT gen_random_uuid();")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();")

    # tenant_company_universe: the radar writes company_domain/signal_type/
    # action/added_at and conflicts on (tenant_id, company_domain), none of
    # which the original (tenant_id, company_id) shape supported.
    op.execute("ALTER TABLE tenant_company_universe ADD COLUMN IF NOT EXISTS company_domain text;")
    op.execute("ALTER TABLE tenant_company_universe ADD COLUMN IF NOT EXISTS signal_type text;")
    op.execute("ALTER TABLE tenant_company_universe ADD COLUMN IF NOT EXISTS action text;")
    op.execute(
        "ALTER TABLE tenant_company_universe "
        "ADD COLUMN IF NOT EXISTS added_at timestamptz DEFAULT now();"
    )
    op.execute("DELETE FROM tenant_company_universe WHERE company_domain IS NULL;")
    # Drop the old (tenant_id, company_id) PK first: company_id cannot become
    # nullable while it is still part of a primary key.
    op.execute("ALTER TABLE tenant_company_universe DROP CONSTRAINT IF EXISTS tenant_company_universe_pkey;")
    op.execute("ALTER TABLE tenant_company_universe ALTER COLUMN company_domain SET NOT NULL;")
    op.execute("ALTER TABLE tenant_company_universe ALTER COLUMN company_id DROP NOT NULL;")
    op.execute(
        "ALTER TABLE tenant_company_universe "
        "ADD PRIMARY KEY (tenant_id, company_domain);"
    )

    # The single-session-var RLS scheme is only coherent when a tenant's id
    # and its user_id are the same value — make that explicit.
    op.execute(
        "ALTER TABLE tenants ADD CONSTRAINT tenants_id_matches_user_id CHECK (id = user_id);"
    )

    # New durable action queue, RLS-isolated like every other tenant table.
    op.execute(ACTION_QUEUE_DDL)
    op.execute(ACTION_QUEUE_INDEX_DDL)
    for statement in generate_rls_sql("action_queue"):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS action_queue CASCADE;")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_id_matches_user_id;")
    op.execute("ALTER TABLE tenant_company_universe DROP CONSTRAINT IF EXISTS tenant_company_universe_pkey;")
    op.execute("ALTER TABLE tenant_company_universe DROP COLUMN IF EXISTS added_at;")
    op.execute("ALTER TABLE tenant_company_universe DROP COLUMN IF EXISTS action;")
    op.execute("ALTER TABLE tenant_company_universe DROP COLUMN IF EXISTS signal_type;")
    op.execute("ALTER TABLE tenant_company_universe DROP COLUMN IF EXISTS company_domain;")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS updated_at;")
    op.execute("ALTER TABLE companies ALTER COLUMN id DROP DEFAULT;")
