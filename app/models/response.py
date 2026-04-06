from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel


class MetricResult(BaseModel):
    score: Optional[float] = None
    reason: Optional[Any] = None

    model_config = {"extra": "allow"}


class EvalMetadata(BaseModel):
    evaluator_type: str
    metric_name: str
    eval_latency_s: float
    evaluated_at: datetime


class EvaluateResponse(BaseModel):
    eval_id: UUID
    status: str  # "success" | "failed"
    result: Optional[MetricResult] = None
    metadata: Optional[EvalMetadata] = None


class ErrorResponse(BaseModel):
    error: str
    message: Optional[str] = None
    detail: Optional[List[Any]] = None
    eval_id: Optional[UUID] = None


class BatchItemResult(BaseModel):
    """Per-metric result within a batch response."""

    eval_id: UUID
    metric_name: str
    status: str  # "success" | "failed"
    result: Optional[MetricResult] = None
    metadata: Optional[EvalMetadata] = None
    error: Optional[str] = None
    message: Optional[str] = None


class BatchEvaluateResponse(BaseModel):
    """Response model for batch evaluation."""

    task_id: UUID
    results: List[BatchItemResult]
