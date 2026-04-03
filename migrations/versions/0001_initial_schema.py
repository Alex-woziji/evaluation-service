"""Initial schema: eval_log and llm_call_log

Revision ID: 0001
Revises:
Create Date: 2025-04-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("metric_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("scores_detail", postgresql.JSONB, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("error_type", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("eval_latency_ms", sa.Integer, nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "llm_call_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "eval_log_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_log.id"),
            nullable=False,
        ),
        sa.Column("judge_model", sa.String(128), nullable=False),
        sa.Column("prompt_system", sa.Text, nullable=True),
        sa.Column("prompt_user", sa.Text, nullable=True),
        sa.Column("raw_response", postgresql.JSONB, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("llm_latency_ms", sa.Integer, nullable=True),
        sa.Column("attempt_number", sa.SmallInteger, nullable=False),
    )

    op.create_index("ix_llm_call_log_eval_log_id", "llm_call_log", ["eval_log_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_call_log_eval_log_id", table_name="llm_call_log")
    op.drop_table("llm_call_log")
    op.drop_table("eval_log")
