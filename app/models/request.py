from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RecordIn(BaseModel):
    input: str = Field(..., min_length=1)
    output: str = Field(..., min_length=1)
    reference: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvalConfigIn(BaseModel):
    judge_model: Optional[str] = None
    criteria: List[str] = Field(default_factory=list)
    rubric: Optional[str] = None
    score_range: Dict[str, float] = Field(default_factory=lambda: {"min": 0.0, "max": 1.0})
    language: str = "zh"

    model_config = {"extra": "allow"}

    @field_validator("score_range")
    @classmethod
    def validate_score_range(cls, v: Dict[str, float]) -> Dict[str, float]:
        if "min" not in v or "max" not in v:
            raise ValueError("score_range must have 'min' and 'max' keys")
        if v["min"] >= v["max"]:
            raise ValueError("score_range min must be less than max")
        return v


class EvaluateRequest(BaseModel):
    eval_id: UUID
    metric_type: str = Field(..., min_length=1)
    record: RecordIn
    eval_config: EvalConfigIn
