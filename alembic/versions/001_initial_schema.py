"""Initial schema and RLS.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-08-09 01:31:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.models import ALL_DDL
from jobos.db.rls import TENANT_TABLES, generate_rls_sql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ensure pgvector extension is available
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    # 2. Create tables
    for ddl in ALL_DDL:
        op.execute(ddl)
        
    # 3. Apply RLS
    for table_name in TENANT_TABLES:
        for statement in generate_rls_sql(table_name):
            op.execute(statement)


def downgrade() -> None:
    # 1. Drop RLS policies
    for table_name in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY;")
        
    # 2. Drop tables in reverse order of creation
    op.execute("DROP TABLE IF EXISTS tenant_company_universe CASCADE;")
    op.execute("DROP TABLE IF EXISTS agent_decisions CASCADE;")
    op.execute("DROP TABLE IF EXISTS outbox CASCADE;")
    op.execute("DROP TABLE IF EXISTS referral_sequences CASCADE;")
    op.execute("DROP TABLE IF EXISTS people CASCADE;")
    op.execute("DROP TABLE IF EXISTS applications CASCADE;")
    op.execute("DROP TABLE IF EXISTS matches CASCADE;")
    op.execute("DROP TABLE IF EXISTS cg_bullets CASCADE;")
    op.execute("DROP TABLE IF EXISTS credentials CASCADE;")
    op.execute("DROP TABLE IF EXISTS tenant_keys CASCADE;")
    op.execute("DROP TABLE IF EXISTS tenants CASCADE;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")
    op.execute("DROP TABLE IF EXISTS suppression_list CASCADE;")
    op.execute("DROP TABLE IF EXISTS job_requirements CASCADE;")
    op.execute("DROP TABLE IF EXISTS jobs CASCADE;")
    op.execute("DROP TABLE IF EXISTS companies CASCADE;")
