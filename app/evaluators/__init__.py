from app.evaluators.registry import evaluator_registry

# Register evaluator types — each import triggers its sub-package init
from app.evaluators.llm_judge import llm_judge_registry
from app.evaluators.performance import performance_registry

evaluator_registry.register_type("llm_judge", llm_judge_registry)
evaluator_registry.register_type("performance", performance_registry)


if __name__ == "__main__":
    for eval_type in evaluator_registry.list_types():
        print(f"\n[{eval_type}]")
        for name in evaluator_registry.list_metrics(eval_type):
            m = evaluator_registry.get(eval_type, name)
            print(f"  {name}: required={m.required_fields}, optional={getattr(m, 'optional_fields', [])}")

