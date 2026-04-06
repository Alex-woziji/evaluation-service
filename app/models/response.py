from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

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


# ── LLM Config Override ───────────────────────────────────────────────────────


class LLMConfig(BaseModel):
    """Per-request LLM configuration override. Priority: API param > env var > default."""

    model: Optional[str] = Field(None, description="Model deployment name, overrides LLM_MODEL env var")
    temperature: Optional[float] = Field(None, description="Generation temperature, overrides LLM_TEMPERATURE env var")


# ── Batch models ──────────────────────────────────────────────────────────────


class BatchEvaluateRequest(BaseModel):
    """Request model for batch evaluation."""

    task_id: UUID = Field(default_factory=uuid4, description="Task ID shared across all metrics in the batch, auto-generated if not provided")
    metrics: List[str] = Field(..., min_length=1, description="List of metric names to evaluate concurrently")
    test_case: Dict[str, Any] = Field(..., description="Loose dict containing fields for all metrics")
    llm_config: Optional[LLMConfig] = Field(None, description="Per-request LLM config override (model, temperature)")


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
