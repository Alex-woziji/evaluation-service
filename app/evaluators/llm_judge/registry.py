"""LLM Judge sub-registry — just a MetricRegistry singleton."""

from app.evaluators.registry import MetricRegistry

llm_judge_registry = MetricRegistry()
