"""harden rls empty string tenant guard

Revision ID: 00de666cafd0
Revises: 001_initial_schema
Create Date: 2026-08-09 20:34:59.657669

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.rls import TENANT_TABLES, generate_rls_sql

# revision identifiers, used by Alembic.
revision: str = '00de666cafd0'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Re-create every tenant_isolation_policy so an empty-string
    # jobos.tenant_id is treated like NULL (zero rows) instead of crashing
    # on the ''::uuid cast — see jobos/db/rls.py for the NULLIF predicate.
    for table_name in TENANT_TABLES:
        for statement in generate_rls_sql(table_name):
            op.execute(statement)


def downgrade() -> None:
    # Revert to the pre-hardening predicate (crashes on empty-string tenant
    # instead of returning zero rows).
    for table_name in TENANT_TABLES:
        if table_name in ("credentials", "tenant_keys", "tenant_company_universe"):
            col_name = "tenant_id"
        elif table_name == "users":
            col_name = "id"
        else:
            col_name = "user_id"
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_policy ON {table_name}
            USING (
                current_setting('jobos.tenant_id', true) IS NOT NULL
                AND {col_name} = current_setting('jobos.tenant_id', true)::uuid
            );
            """
        )
