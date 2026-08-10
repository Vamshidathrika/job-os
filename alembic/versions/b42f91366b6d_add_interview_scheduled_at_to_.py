"""add interview_scheduled_at to applications

Revision ID: b42f91366b6d
Revises: 9e8d7e91fe2a
Create Date: 2026-08-10 10:17:17.117010

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b42f91366b6d'
down_revision: Union[str, None] = '9e8d7e91fe2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Needed to compute time-to-interview on the dashboard; without it the
    # metric had no source column and was reported from mock data.
    op.execute(
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS interview_scheduled_at timestamptz;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE applications DROP COLUMN IF EXISTS interview_scheduled_at;")
