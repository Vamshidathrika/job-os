"""add api_token_audit table

Revision ID: 1b31222fd092
Revises: 7b2ed0f4a296
Create Date: 2026-08-12 22:23:37.163518

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.models import API_TOKEN_AUDIT_DDL


# revision identifiers, used by Alembic.
revision: str = '1b31222fd092'
down_revision: Union[str, None] = '7b2ed0f4a296'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally no RLS: authentication must resolve a tenant before any
    # tenant context exists to filter by (same reasoning as api_tokens).
    op.execute(API_TOKEN_AUDIT_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_token_audit CASCADE;")
