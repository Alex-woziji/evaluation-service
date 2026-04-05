"""Rename PK columns: evaluation_result.id → eval_id, llm_metadata.id → metadata_id

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-05 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("evaluation_result", "id", new_column_name="eval_id")
    op.alter_column("llm_metadata", "id", new_column_name="metadata_id")


def downgrade() -> None:
    op.alter_column("llm_metadata", "metadata_id", new_column_name="id")
    op.alter_column("evaluation_result", "eval_id", new_column_name="id")
