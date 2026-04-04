# Evaluators

This folder contains the evaluator framework for evaluation-service.

## Architecture

```
criteria.py              CriteriaType enum — all supported evaluation criteria
registry.py              EvaluatorRegistry — evaluator + criteria lookup
base.py                  BaseEvaluator, EvalRecord, EvalConfig, EvalResult
llm_judge_evaluator.py   LLM-based judge evaluator (metric_type="llm_judge")
__init__.py              Imports evaluators to trigger @registry.register
```

## Two registration layers

### 1. Metric types (`metric_type`)

Each evaluator class sets a unique `metric_type` string and registers via `@registry.register`:

```python
from app.evaluators.base import BaseEvaluator
from app.evaluators.registry import registry

@registry.register
class MyEvaluator(BaseEvaluator):
    metric_type = "my_metric"

    async def evaluate(self, record, config):
        ...
```

The API route resolves `request.metric_type` → `registry.get(metric_type)`. Unregistered types return `422 UNKNOWN_METRIC_TYPE`.

### 2. Criteria (`CriteriaType` enum)

Criteria are the fine-grained dimensions an evaluator scores (e.g. `accuracy`, `clarity`). They are registered centrally as an enum in `criteria.py`:

```python
class CriteriaType(str, Enum):
    accuracy = "accuracy"
    completeness = "completeness"
    clarity = "clarity"
```

The API rejects any criterion not in this enum with `422 CRITERIA_VALIDATION_ERROR`.

**To add a new criterion**, add one line to `CriteriaType` in `criteria.py`.

## Validation hooks

`BaseEvaluator` provides two overridable hooks that run before evaluation:

### `validate_record(record: dict, config: EvalConfig)`

Validate that the incoming `record` dict contains the fields required by your metric/criteria combination. Raise `RecordValidationError(field="record.xxx", message="...")` on failure.

Example — `accuracy` requires `reference`:

```python
def validate_record(self, record, config):
    if "accuracy" in config.criteria:
        ref = record.get("reference")
        if not isinstance(ref, str) or not ref.strip():
            raise RecordValidationError(
                "reference is required when criteria includes accuracy",
                field="record.reference",
            )
```

### `validate_config(config: EvalConfig)`

Validate evaluator-specific config fields. Raise `ConfigValidationError(field="eval_config.xxx", message="...")` on failure.

Example — `llm_judge` requires `judge_model` and non-empty `criteria`:

```python
def validate_config(self, config):
    if not config.judge_model:
        raise ConfigValidationError(
            "judge_model is required for llm_judge",
            field="eval_config.judge_model",
        )
```

## Validation order in the API

1. Pydantic parses `EvaluateRequest` (structural validation).
2. `registry.get(metric_type)` — `422 UNKNOWN_METRIC_TYPE` if not registered.
3. Criteria enum check — `422 CRITERIA_VALIDATION_ERROR` if any criterion is unsupported.
4. `evaluator.validate_record(record, config)` — `422 RECORD_VALIDATION_ERROR`.
5. `evaluator.validate_config(config)` — `422 CONFIG_VALIDATION_ERROR`.
6. `evaluator.evaluate(record, config)` — runs evaluation.

## How to add a new evaluator

1. Create a new file, e.g. `app/evaluators/performance_evaluator.py`.
2. Define the class:

```python
from app.evaluators.base import BaseEvaluator, EvalConfig, EvalRecord, EvalResult
from app.evaluators.registry import registry

@registry.register
class PerformanceEvaluator(BaseEvaluator):
    metric_type = "performance"

    def validate_record(self, record, config):
        # check required record fields for this metric
        ...

    def validate_config(self, config):
        # check required config fields for this metric
        ...

    async def evaluate(self, record: EvalRecord, config: EvalConfig) -> EvalResult:
        ...
```

3. Import it in `app/evaluators/__init__.py` to trigger registration:

```python
from app.evaluators import performance_evaluator  # noqa: F401
```

4. If the evaluator introduces new criteria, add them to `CriteriaType` in `criteria.py`.
5. If a criterion requires specific record fields, enforce that in `validate_record`.

## How to add a new criterion

1. Add the value to `CriteriaType` in `criteria.py`.
2. If it requires specific record fields, add the check in the relevant evaluator's `validate_record`.
3. Add tests covering:
   - Criterion is accepted when valid.
   - Missing required record fields return `422 RECORD_VALIDATION_ERROR`.
   - Unregistered criteria return `422 CRITERIA_VALIDATION_ERROR`.

## Data flow: request record → EvalRecord

The API receives `record` as a generic `Dict[str, Any]`. The route handler maps it to the internal `EvalRecord` dataclass after validation passes:

```python
record = EvalRecord(
    input=request.record["input"],
    output=request.record["output"],
    reference=request.record.get("reference"),
    metadata={
        k: v for k, v in request.record.items()
        if k not in {"input", "output", "reference"}
    },
)
```

All extra fields from the request record are preserved in `EvalRecord.metadata`.

## Error codes

| Error code | HTTP | Trigger |
|---|---|---|
| `UNKNOWN_METRIC_TYPE` | 422 | `metric_type` not in registry |
| `CRITERIA_VALIDATION_ERROR` | 422 | criterion not in `CriteriaType` enum |
| `RECORD_VALIDATION_ERROR` | 422 | record missing fields required by criterion |
| `CONFIG_VALIDATION_ERROR` | 422 | evaluator-specific config invalid |
