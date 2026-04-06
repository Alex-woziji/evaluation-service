from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ── LLM Config Override ───────────────────────────────────────────────────────


class LLMConfig(BaseModel):
    """Per-request LLM configuration override. Priority: API param > env var > default."""

    model: Optional[str] = Field(None, description="Model deployment name, overrides LLM_MODEL env var")
    temperature: Optional[float] = Field(None, description="Generation temperature, overrides LLM_TEMPERATURE env var")


# ── Batch Request ──────────────────────────────────────────────────────────────


class BatchEvaluateRequest(BaseModel):
    """Request model for batch evaluation."""

    task_id: UUID = Field(default_factory=uuid4, description="Task ID shared across all metrics in the batch, auto-generated if not provided")
    metrics: List[str] = Field(..., min_length=1, description="List of metric names to evaluate concurrently")
    test_case: Dict[str, Any] = Field(..., description="Loose dict containing fields for all metrics")
    llm_config: Optional[LLMConfig] = Field(None, description="Per-request LLM config override (model, temperature)")


class ValidationErrorDetail(BaseModel):
    field: str
    message: str
