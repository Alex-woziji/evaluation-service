"""
Unit tests for EvaluatorRegistry.
"""
from __future__ import annotations

import pytest

from app.evaluators.base import BaseEvaluator, EvalConfig, EvalRecord, EvalResult
from app.evaluators.registry import EvaluatorRegistry


class _DummyEvaluator(BaseEvaluator):
    metric_type = "dummy"

    async def evaluate(self, record: EvalRecord, config: EvalConfig) -> EvalResult:
        return EvalResult(score=1.0, scores_detail={}, retry_count=0, eval_latency_ms=0)


class TestEvaluatorRegistry:
    def test_register_and_get(self):
        reg = EvaluatorRegistry()
        reg.register(_DummyEvaluator)
        evaluator = reg.get("dummy")
        assert evaluator is not None
        assert isinstance(evaluator, _DummyEvaluator)

    def test_get_unknown_returns_none(self):
        reg = EvaluatorRegistry()
        assert reg.get("nonexistent") is None

    def test_list_registered(self):
        reg = EvaluatorRegistry()
        reg.register(_DummyEvaluator)
        assert "dummy" in reg.list_registered()

    def test_register_empty_metric_type_raises(self):
        class _BadEvaluator(BaseEvaluator):
            metric_type = ""

            async def evaluate(self, record, config):
                pass

        reg = EvaluatorRegistry()
        with pytest.raises(ValueError, match="must define a non-empty metric_type"):
            reg.register(_BadEvaluator)

    def test_global_registry_has_llm_judge(self):
        # Import triggers registration via app/evaluators/__init__.py
        import app.evaluators  # noqa: F401
        from app.evaluators.registry import registry

        assert "llm_judge" in registry.list_registered()


class TestCriteriaValidation:
    def test_supported_criterion(self):
        from app.evaluators.registry import EvaluatorRegistry
        reg = EvaluatorRegistry()
        assert reg.is_supported_criterion("accuracy") is True
        assert reg.is_supported_criterion("completeness") is True
        assert reg.is_supported_criterion("clarity") is True

    def test_unsupported_criterion(self):
        from app.evaluators.registry import EvaluatorRegistry
        reg = EvaluatorRegistry()
        assert reg.is_supported_criterion("nonexistent") is False

    def test_list_supported_criteria(self):
        from app.evaluators.registry import EvaluatorRegistry
        reg = EvaluatorRegistry()
        criteria = reg.list_supported_criteria()
        assert "accuracy" in criteria
        assert "completeness" in criteria
        assert "clarity" in criteria
