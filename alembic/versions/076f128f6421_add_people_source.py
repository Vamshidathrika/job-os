"""add people.source

Revision ID: 076f128f6421
Revises: 2acad92b4115
Create Date: 2026-08-10 21:06:54.644797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '076f128f6421'
down_revision: Union[str, None] = '2acad92b4115'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Provenance for a contact: 'linkedin_connection', 'apollo', etc.
    op.execute("ALTER TABLE people ADD COLUMN IF NOT EXISTS source text;")


def downgrade() -> None:
    op.execute("ALTER TABLE people DROP COLUMN IF EXISTS source;")
