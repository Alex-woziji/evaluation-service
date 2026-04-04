from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class EvaluateResponse(BaseModel):
    eval_id: UUID
    evaluator_type: str
    metric_name: str
    status: str  # "success"
    score: Optional[float] = None

    detail: Optional[Dict[str, Any]] = None
    reasoning: Optional[Any] = None
    eval_latency_ms: int
    evaluated_at: datetime


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    error: str
    message: Optional[str] = None
    detail: Optional[List[ValidationErrorDetail]] = None
    eval_id: Optional[UUID] = None
