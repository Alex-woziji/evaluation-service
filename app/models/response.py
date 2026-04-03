from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class EvaluateResponse(BaseModel):
    eval_id: UUID
    metric_type: str
    status: str  # "success"
    score: float
    scores_detail: Dict[str, float]
    reasoning: Optional[str] = None
    raw_output: Optional[Dict[str, Any]] = None
    retry_count: int
    eval_latency_ms: int
    evaluated_at: datetime


class ValidationErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    error: str
    message: Optional[str] = None
    detail: Optional[List[ValidationErrorDetail]] = None
    retry_count: Optional[int] = None
    eval_id: Optional[UUID] = None
