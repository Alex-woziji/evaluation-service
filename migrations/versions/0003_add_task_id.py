"""Add task_id column to evaluation_result

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-05 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evaluation_result",
        sa.Column("task_id", sa.String(36), nullable=True),
    )
    op.create_index("ix_evaluation_result_task_id", "evaluation_result", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_result_task_id", table_name="evaluation_result")
    op.drop_column("evaluation_result", "task_id")
