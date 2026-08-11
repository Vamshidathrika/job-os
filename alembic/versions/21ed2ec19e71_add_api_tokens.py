"""add api_tokens

Revision ID: 21ed2ec19e71
Revises: 076f128f6421
Create Date: 2026-08-11 13:09:33.158110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.models import API_TOKENS_DDL, API_TOKENS_INDEX_DDL


# revision identifiers, used by Alembic.
revision: str = '21ed2ec19e71'
down_revision: Union[str, None] = '076f128f6421'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentionally no RLS: authentication must resolve a tenant before any
    # tenant context exists to filter by. Only the token's SHA-256 is stored.
    op.execute(API_TOKENS_DDL)
    op.execute(API_TOKENS_INDEX_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_tokens CASCADE;")
