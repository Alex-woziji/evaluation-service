from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    error: str
    message: Optional[str] = None
    detail: Optional[List[ValidationErrorDetail]] = None
    eval_id: Optional[UUID] = None
