from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class EvaluationResult(Base):
    __tablename__ = "evaluation_result"

    id = Column(String(36), primary_key=True)  # = eval_id passed in by scheduler
    metric_type = Column(String(64), nullable=False)  # evaluator_type (e.g. "llm_judge")
    metric_name = Column(String(64), nullable=True)  # e.g. "faithfulness"
    status = Column(String(16), nullable=False)  # "success" | "failed"
    score = Column(Float, nullable=True)
    reason = Column(JSON, nullable=True)
    error_type = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    eval_latency_s = Column(Float, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    llm_metadatas = relationship(
        "LLMMetadata", back_populates="evaluation_result", cascade="all, delete-orphan"
    )


class LLMMetadata(Base):
    __tablename__ = "llm_metadata"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    evaluation_result_id = Column(String(36), ForeignKey("evaluation_result.id"), nullable=False)
    judge_model = Column(String(128), nullable=False)
    prompt_system = Column(Text, nullable=True)
    prompt_user = Column(Text, nullable=True)
    raw_response = Column(JSON, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    llm_latency_s = Column(Float, nullable=True)
    attempt_number = Column(SmallInteger, nullable=False)

    evaluation_result = relationship("EvaluationResult", back_populates="llm_metadatas")

    __table_args__ = (Index("ix_llm_metadata_evaluation_result_id", "evaluation_result_id"),)
