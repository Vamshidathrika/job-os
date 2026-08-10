"""embedding dim 384 for local model

Revision ID: 2acad92b4115
Revises: 9d4f8cf00f5b
Create Date: 2026-08-10 21:00:31.805997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.models import EMBEDDING_DIM


# revision identifiers, used by Alembic.
revision: str = '2acad92b4115'
down_revision: Union[str, None] = '9d4f8cf00f5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing vectors are the wrong width for the new model, and a vector
    # column cannot be re-typed while populated with a different dimension.
    op.execute("UPDATE jobs SET embedding = NULL;")
    op.execute(f"ALTER TABLE jobs ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM});")


def downgrade() -> None:
    op.execute("UPDATE jobs SET embedding = NULL;")
    op.execute("ALTER TABLE jobs ALTER COLUMN embedding TYPE vector(768);")
