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


class EvalLog(Base):
    __tablename__ = "eval_log"

    id = Column(String(36), primary_key=True)  # = eval_id passed in by scheduler
    metric_type = Column(String(64), nullable=False)  # evaluator_type (e.g. "llm_judge")
    metric_name = Column(String(64), nullable=True)  # e.g. "faithfulness"
    status = Column(String(16), nullable=False)  # "success" | "failed"
    score = Column(Float, nullable=True)
    scores_detail = Column(JSON, nullable=True)
    reasoning = Column(Text, nullable=True)
    error_type = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(SmallInteger, nullable=False, default=0)
    eval_latency_s = Column(Float, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    llm_call_logs = relationship(
        "LLMCallLog", back_populates="eval_log", cascade="all, delete-orphan"
    )


class LLMCallLog(Base):
    __tablename__ = "llm_call_log"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    eval_log_id = Column(String(36), ForeignKey("eval_log.id"), nullable=False)
    judge_model = Column(String(128), nullable=False)
    prompt_system = Column(Text, nullable=True)
    prompt_user = Column(Text, nullable=True)
    raw_response = Column(JSON, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    llm_latency_ms = Column(Integer, nullable=True)
    attempt_number = Column(SmallInteger, nullable=False)

    eval_log = relationship("EvalLog", back_populates="llm_call_logs")

    __table_args__ = (Index("ix_llm_call_log_eval_log_id", "eval_log_id"),)
