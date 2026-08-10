"""fix jobs table id default ats_type and embedding dim

Revision ID: 7ab0f93b11ea
Revises: 00de666cafd0
Create Date: 2026-08-10 09:57:26.368463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.models import EMBEDDING_DIM


# revision identifiers, used by Alembic.
revision: str = '7ab0f93b11ea'
down_revision: Union[str, None] = '00de666cafd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # jobs.id had no default, so every ingestion INSERT (which omits id)
    # violated NOT NULL and was swallowed by the worker's per-job except.
    op.execute("ALTER TABLE jobs ALTER COLUMN id SET DEFAULT gen_random_uuid();")
    # The worker writes ats_type, but the column never existed.
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS ats_type text;")
    # Column width must match the configured embedding model
    # (bge-base-en-v1.5 = 768), not the 1536 of an OpenAI-style model.
    op.execute(f"ALTER TABLE jobs ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM});")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs ALTER COLUMN embedding TYPE vector(1536);")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS ats_type;")
    op.execute("ALTER TABLE jobs ALTER COLUMN id DROP DEFAULT;")
