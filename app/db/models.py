from __future__ import annotations

import uuid

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class EvalLog(Base):
    __tablename__ = "eval_log"

    id = Column(PGUUID(as_uuid=True), primary_key=True)  # = eval_id passed in by scheduler
    metric_type = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False)  # "success" | "failed"
    score = Column(Float, nullable=True)
    scores_detail = Column(JSONB, nullable=True)
    reasoning = Column(Text, nullable=True)
    error_type = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(SmallInteger, nullable=False, default=0)
    eval_latency_ms = Column(Integer, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    llm_call_logs = relationship(
        "LLMCallLog", back_populates="eval_log", cascade="all, delete-orphan"
    )


class LLMCallLog(Base):
    __tablename__ = "llm_call_log"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eval_log_id = Column(
        PGUUID(as_uuid=True), ForeignKey("eval_log.id"), nullable=False
    )
    judge_model = Column(String(128), nullable=False)
    prompt_system = Column(Text, nullable=True)
    prompt_user = Column(Text, nullable=True)
    raw_response = Column(JSONB, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    llm_latency_ms = Column(Integer, nullable=True)
    attempt_number = Column(SmallInteger, nullable=False)

    eval_log = relationship("EvalLog", back_populates="llm_call_logs")

    __table_args__ = (Index("ix_llm_call_log_eval_log_id", "eval_log_id"),)
