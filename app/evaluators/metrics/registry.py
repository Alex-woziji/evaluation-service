"""Central registry for metrics — discovery, validation, and record checking."""

from __future__ import annotations

from app.utils.logger import get_logger

logger = get_logger(__name__)

_REQUIRED_ATTRS = ("name", "required_fields", "evaluate")


class MetricRegistry:
    """Registry that holds all metric instances and validates them on registration."""

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


# Global singleton
metric_registry = MetricRegistry()
