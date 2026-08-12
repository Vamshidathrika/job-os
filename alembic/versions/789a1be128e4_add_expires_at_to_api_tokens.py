"""add expires_at to api_tokens

Revision ID: 789a1be128e4
Revises: 21ed2ec19e71
Create Date: 2026-08-12 22:15:34.100947

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.models import API_TOKENS_EXPIRES_AT_DDL


# revision identifiers, used by Alembic.
revision: str = '789a1be128e4'
down_revision: Union[str, None] = '21ed2ec19e71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL means the token never expires — same behavior as before this
    # column existed, so no backfill is needed for existing rows.
    op.execute(API_TOKENS_EXPIRES_AT_DDL)


def downgrade() -> None:
    op.execute("ALTER TABLE api_tokens DROP COLUMN IF EXISTS expires_at;")
