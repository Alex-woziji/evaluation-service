"""Performance sub-registry — just a MetricRegistry singleton."""

from app.evaluators.registry import MetricRegistry

performance_registry = MetricRegistry()
