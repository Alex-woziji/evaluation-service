from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MetricRequest(BaseModel):
    """Request body for per-metric endpoints."""
    eval_id: UUID
    record: Dict[str, Any]
    options: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("record")
    @classmethod
    def validate_record(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("record must be an object")
        return v
