# Import all evaluators here to trigger their @registry.register decorators.
# Add a new import line whenever a new evaluator is created.
from app.evaluators import llm_judge_evaluator  # noqa: F401
