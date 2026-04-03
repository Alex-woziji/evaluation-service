from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvalRecord:
    input: str
    output: str
    reference: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalConfig:
    judge_model: str = ""
    criteria: List[str] = field(default_factory=list)
    rubric: Optional[str] = None
    score_range: Dict[str, float] = field(default_factory=lambda: {"min": 0.0, "max": 1.0})
    language: str = "zh"
    extra: Dict[str, Any] = field(default_factory=dict)  # metric-specific params


@dataclass
class EvalResult:
    score: float
    scores_detail: Dict[str, float]
    retry_count: int
    eval_latency_ms: int
    reasoning: Optional[str] = None
    raw_output: Optional[Dict[str, Any]] = None
    # Populated by llm_judge for persistence
    llm_call_data: Optional[List[Dict[str, Any]]] = None


class BaseEvaluator(ABC):
    metric_type: str = ""

    def validate_config(self, config: EvalConfig) -> None:
        """
        Validate metric-specific config fields.
        Raise ConfigValidationError on failure.
        Default: no-op (subclasses override as needed).
        """
        pass

    @abstractmethod
    async def evaluate(self, record: EvalRecord, config: EvalConfig) -> EvalResult:
        """Execute evaluation with internal retry. Raise EvaluationError on final failure."""
        ...
