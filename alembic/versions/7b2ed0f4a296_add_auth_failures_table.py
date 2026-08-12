"""add auth_failures table

Revision ID: 7b2ed0f4a296
Revises: 789a1be128e4
Create Date: 2026-08-12 22:20:20.439473

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.models import AUTH_FAILURES_DDL, AUTH_FAILURES_INDEX_DDL


# revision identifiers, used by Alembic.
revision: str = '7b2ed0f4a296'
down_revision: Union[str, None] = '789a1be128e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally no RLS: authentication must resolve a tenant before any
    # tenant context exists to filter by (same reasoning as api_tokens).
    op.execute(AUTH_FAILURES_DDL)
    op.execute(AUTH_FAILURES_INDEX_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS auth_failures CASCADE;")
