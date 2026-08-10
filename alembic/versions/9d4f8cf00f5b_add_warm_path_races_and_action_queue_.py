"""add warm_path_races and action_queue scheduled_for

Revision ID: 9d4f8cf00f5b
Revises: b42f91366b6d
Create Date: 2026-08-10 15:40:50.656402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from jobos.db.models import (
    ACTION_QUEUE_INDEX_DDL,
    WARM_PATH_RACES_DDL,
    WARM_PATH_RACES_INDEX_DDL,
)
from jobos.db.rls import generate_rls_sql


# revision identifiers, used by Alembic.
revision: str = '9d4f8cf00f5b'
down_revision: Union[str, None] = 'b42f91366b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delayed work (the 3-touch sequence lands on day 0, 3 and 6) was
    # impossible without an eligibility timestamp.
    op.execute("ALTER TABLE action_queue ADD COLUMN IF NOT EXISTS scheduled_for timestamptz;")
    op.execute("DROP INDEX IF EXISTS action_queue_band_status_idx;")
    op.execute(ACTION_QUEUE_INDEX_DDL)

    op.execute(WARM_PATH_RACES_DDL)
    op.execute(WARM_PATH_RACES_INDEX_DDL)
    for statement in generate_rls_sql("warm_path_races"):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS warm_path_races CASCADE;")
    op.execute("DROP INDEX IF EXISTS action_queue_band_status_idx;")
    op.execute("ALTER TABLE action_queue DROP COLUMN IF EXISTS scheduled_for;")
    op.execute(
        "CREATE INDEX IF NOT EXISTS action_queue_band_status_idx "
        "ON action_queue (user_id, band, status, created_at);"
    )
