"""Evaluator registries — shared MetricRegistry + top-level EvaluatorRegistry."""

from __future__ import annotations

from app.utils.logger import get_logger

logger = get_logger(__name__)

_REQUIRED_ATTRS = ("name", "required_fields", "evaluate")


# ---------- Shared sub-registry ----------

class MetricRegistry:
    """Generic sub-registry for metrics of any evaluator type.

    Provides duck-typing validation on ``register()``, field checking on
    ``validate_record()``, and lookup by name.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, object] = {}

    def register(self, metric: object) -> None:
        """Register a metric instance after duck-typing validation.

        Raises
        ------
        TypeError
            If the metric is missing any of ``name``, ``required_fields``, ``evaluate``.
        """
        missing = [attr for attr in _REQUIRED_ATTRS if not hasattr(metric, attr)]
        if missing:
            raise TypeError(
                f"Metric {metric!r} is missing required attributes: {', '.join(missing)}"
            )
        name = metric.name  # type: ignore[attr-defined]
        if name in self._metrics:
            return
        self._metrics[name] = metric
        logger.info("Registered metric: %s", name)

    def get(self, name: str) -> object:
        """Get a metric by name.

        Raises
        ------
        KeyError
            If no metric with the given name is registered.
        """
        if name not in self._metrics:
            raise KeyError(f"Metric {name!r} not found in registry")
        return self._metrics[name]

    def validate_record(self, name: str, record: dict) -> None:
        """Check that *record* contains all fields required by the named metric.

        Raises
        ------
        KeyError
            If the metric is not registered.
        ValueError
            If *record* is missing required fields.
        """
        metric = self.get(name)
        required: list[str] = metric.required_fields  # type: ignore[attr-defined]
        missing = [f for f in required if f not in record]
        if missing:
            raise ValueError(
                f"Metric {name!r} requires fields {missing}, "
                f"but record only has {list(record)}"
            )

    def list_metrics(self) -> list[str]:
        """Return names of all registered metrics."""
        return list(self._metrics)


# ---------- Top-level router ----------

class EvaluatorRegistry:
    """Routes evaluator calls by type (e.g. ``llm_judge``, ``performance``).

    Each evaluator type registers a sub-registry that provides
    ``get(name)``, ``validate_record(name, record)``, and ``list_metrics()``.
    """

    def __init__(self) -> None:
        self._sub_registries: dict[str, MetricRegistry] = {}

    def register_type(self, evaluator_type: str, sub_registry: MetricRegistry) -> None:
        """Register a sub-registry for an evaluator type."""
        if evaluator_type in self._sub_registries:
            return
        self._sub_registries[evaluator_type] = sub_registry
        logger.info("Registered evaluator type: %s", evaluator_type)

    def get_sub_registry(self, evaluator_type: str) -> MetricRegistry:
        """Get the sub-registry for a given evaluator type.

        Raises
        ------
        KeyError
            If the evaluator type is not registered.
        """
        if evaluator_type not in self._sub_registries:
            allowed = ", ".join(self._sub_registries) or "(none)"
            raise KeyError(
                f"Unknown evaluator type {evaluator_type!r}. "
                f"Allowed types: {allowed}"
            )
        return self._sub_registries[evaluator_type]

    def get(self, evaluator_type: str, name: str):
        """Get a metric by evaluator type and metric name."""
        return self.get_sub_registry(evaluator_type).get(name)

    def validate_record(self, evaluator_type: str, name: str, record: dict) -> None:
        """Validate record fields for a specific metric."""
        self.get_sub_registry(evaluator_type).validate_record(name, record)

    def find_metric(self, name: str) -> tuple[str, object]:
        """Find a metric by name across all evaluator types.

        Returns ``(evaluator_type, metric)``.
        Raises ``KeyError`` if not found.
        """
        for eval_type, sub in self._sub_registries.items():
            if name in sub._metrics:
                return eval_type, sub._metrics[name]
        raise KeyError(f"Metric {name!r} not found in any evaluator type")

    def list_types(self) -> list[str]:
        """Return all registered evaluator types."""
        return list(self._sub_registries)

    def list_metrics(self, evaluator_type: str) -> list[str]:
        """Return all metric names under a given evaluator type."""
        return self.get_sub_registry(evaluator_type).list_metrics()


# Global singleton
evaluator_registry = EvaluatorRegistry()
