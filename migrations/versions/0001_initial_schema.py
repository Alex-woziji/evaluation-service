"""Initial schema: evaluation_result, llm_metadata, llm_prompt

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
        "evaluation_result",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("metric_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("reason", postgresql.JSONB, nullable=True),
        sa.Column("error_type", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("eval_latency_s", sa.Float, nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "llm_metadata",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "evaluation_result_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("evaluation_result.id"),
            nullable=False,
        ),
        sa.Column("judge_model", sa.String(128), nullable=False),
        sa.Column("messages", postgresql.JSONB, nullable=True),
        sa.Column("raw_response", postgresql.JSONB, nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("llm_latency_s", sa.Float, nullable=True),
        sa.Column("attempt_number", sa.SmallInteger, nullable=False),
    )

    op.create_index("ix_llm_metadata_evaluation_result_id", "llm_metadata", ["evaluation_result_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_metadata_evaluation_result_id", table_name="llm_metadata")
    op.drop_table("llm_metadata")
    op.drop_table("evaluation_result")
