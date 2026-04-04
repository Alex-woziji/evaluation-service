from app.evaluators.metrics.FactualCorrectness import FactualCorrectness
from app.evaluators.metrics.Faithfulness import Faithfulness
from app.evaluators.metrics.registry import metric_registry

# Auto-register all metrics on import
metric_registry.register(Faithfulness())
metric_registry.register(FactualCorrectness())


if __name__ == "__main__":
    for name in metric_registry.list_metrics():
        m = metric_registry.get(name)
        print(f'{name}: required={m.required_fields}, optional={getattr(m, "optional_fields", [])}')
