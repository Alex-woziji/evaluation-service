from app.evaluators.llm_judge.FactualCorrectness import FactualCorrectness
from app.evaluators.llm_judge.Faithfulness import Faithfulness
from app.evaluators.llm_judge.registry import llm_judge_registry

# Auto-register all LLM-judge metrics on import
llm_judge_registry.register(Faithfulness())
llm_judge_registry.register(FactualCorrectness())


if __name__ == "__main__":
    for name in llm_judge_registry.list_metrics():
        m = llm_judge_registry.get(name)
        print(f'{name}: required={m.required_fields}, optional={getattr(m, "optional_fields", [])}')
