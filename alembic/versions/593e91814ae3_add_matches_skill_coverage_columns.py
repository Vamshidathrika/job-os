"""add matches skill coverage columns

Revision ID: 593e91814ae3
Revises: 1b31222fd092
Create Date: 2026-08-13 09:52:20.411026

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '593e91814ae3'
down_revision: Union[str, None] = '1b31222fd092'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS skill_coverage float;")
    op.execute("ALTER TABLE matches ADD COLUMN IF NOT EXISTS missing_skills jsonb;")


def downgrade() -> None:
    op.execute("ALTER TABLE matches DROP COLUMN IF EXISTS skill_coverage;")
    op.execute("ALTER TABLE matches DROP COLUMN IF EXISTS missing_skills;")
