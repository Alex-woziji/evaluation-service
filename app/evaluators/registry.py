from __future__ import annotations
import logging
from typing import Dict, List, Optional, Type

from app.evaluators.base import BaseEvaluator
from app.evaluators.criteria import CriteriaType

logger = logging.getLogger(__name__)


class EvaluatorRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, BaseEvaluator] = {}
        self._criteria_registry = {item.value for item in CriteriaType}

    def register(self, cls: Type[BaseEvaluator]) -> Type[BaseEvaluator]:
        """Class decorator to register an evaluator."""
        if not cls.metric_type:
            raise ValueError(f"{cls.__name__} must define a non-empty metric_type")
        instance = cls()
        self._registry[cls.metric_type] = instance
        logger.info("Registered evaluator: %s → %s", cls.metric_type, cls.__name__)
        return cls

    def get(self, metric_type: str) -> Optional[BaseEvaluator]:
        return self._registry.get(metric_type)

    def list_registered(self) -> List[str]:
        return list(self._registry.keys())

    def is_supported_criterion(self, criterion: str) -> bool:
        return criterion in self._criteria_registry

    def list_supported_criteria(self) -> List[str]:
        return sorted(self._criteria_registry)


registry = EvaluatorRegistry()
