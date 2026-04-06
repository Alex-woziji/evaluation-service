# Metrics Architecture Refactoring Task

## Refactoring Goal

Decouple the metrics layer from business logic with three-layer separation of concerns:

```
API Layer (routing/storage) → Registry Layer (discovery/validation) → Metrics Layer (pure evaluation logic)
```

Core Principles:
- Metrics have no business-layer dependencies, only use `call_llm`
- Each metric is a standalone plain class, no base class inheritance, no self-registration
- Registration is centralized in the registry, validated via duck typing (checks name, required_fields, evaluate)
- API layer handles request parsing, response assembly, data persistence

---

## Completed

### 1. Utils Package (`app/utils/`)
- [x] `config.py` — `DBSettings` + `LLMSettings` + `AppSettings` (consolidated from old app/config.py)
- [x] `logger.py` — `get_logger()` generic logger factory
- [x] `llm_utils.py` — `get_llm_client()` + `call_llm(messages, response_format)`
  - Uses `AsyncAzureOpenAI`
  - Built-in exponential backoff retry, does not expose retry_count
  - `response_format` supports dict or pydantic model (auto-uses parse())
  - Non-retryable errors (ValueError/AuthenticationError/BadRequestError) raised immediately
- [x] `llm_tracker.py` — ContextVar-based LLM call metadata tracking
  - `start_tracking()` / `get_tracked_calls()` / `record_call()`
  - Auto-records messages, raw_response, tokens, latency, attempt
  - No changes needed in metric layer, `call_llm()` tracks internally
- [x] `constants.py` — `PROMPT_DIR` + `DEFAULT_DB_PATH` (absolute path based on project root)

### 2. LLM Judge Package (`app/evaluators/llm_judge/`)
- [x] `Faithfulness.py` — `name="faithfulness"`, `required_fields=["response", "retrieved_contexts"]`, `optional_fields=["user_input"]`, `async evaluate()`
- [x] `FactualCorrectness.py` — `name="factual_correctness"`, `required_fields=["reference", "response"]`, `async evaluate()`
- [x] `registry.py` — `llm_judge_registry = MetricRegistry()` sub-registry singleton
- [x] `__init__.py` — import triggers auto-registration of both metrics
- [x] `README.md` — LLM Judge system documentation

### 3. Performance Package (`app/evaluators/performance/`)
- [x] `registry.py` — `performance_registry = MetricRegistry()` empty shell, awaiting formula-based metrics
- [x] `__init__.py` — placeholder registration entry

### 4. Shared Registry (`app/evaluators/registry.py`)
- [x] `MetricRegistry` — generic sub-registry, duck-typing validation + record field validation + list_metrics
- [x] `EvaluatorRegistry` — top-level router, dispatches to sub-registries by evaluator_type (llm_judge/performance)
- [x] `evaluator_registry` global singleton
- [x] `app/evaluators/__init__.py` — register all evaluator types to top-level registry

### 5. API Layer (`app/api/v1/evaluate.py`)
- [x] Dynamic route registration, one route per metric
- [x] Each metric defines its own `request_model` (Pydantic)
- [x] `eval_id` optional (default_factory=uuid4, examples dynamically generated)
- [x] Response format: `{eval_id, status, result: {score, reason, ...}, metadata: {...}}`
- [x] Error mapping: openai exceptions → HTTP status
- [x] LLM call tracking: start/get tracking around evaluate, passed to persist task

### 6. DB Refactoring
- [x] Config consolidation: `app/config.py` deleted, consolidated into `app/utils/config.py` (DBSettings/LLMSettings/AppSettings)
- [x] DB path as constant: `DEFAULT_DB_PATH` in `constants.py`, no longer depends on runtime directory
- [x] Table rename: `eval_log` → `evaluation_result`, `llm_call_log` → `llm_metadata`
- [x] Model rename: `EvalLog` → `EvaluationResult`, `LLMCallLog` → `LLMMetadata`
- [x] Field cleanup: removed `reasoning`, `retry_count`; `scores_detail` → `reason`
- [x] Latency unified: `llm_latency_ms` → `llm_latency_s` (Float)
- [x] `llm_metadata.messages` — JSON column stores raw `[{role, content}, ...]`
- [x] `llm_metadata.raw_response` — stores `{content, model, finish_reason}` (avoids Pydantic serialization warning)
- [x] Persistence transaction: `persist_eval_result` writes evaluation_result + all llm_metadata in a single commit

### 7. Batch API
- [x] `POST /api/v1/evaluation/batch` — accepts list of metric names + loose test_case dict
- [x] `asyncio.gather` runs all metrics concurrently (not serially)
- [x] `task_id` auto-generated if not provided (UUID), shared across metrics in a batch
- [x] Refactored `_evaluate` into `_evaluate_single` returning `BatchItemResult` (no HTTPException)
- [x] Single-metric routes adapt `_evaluate_single`, keeping existing behavior
- [x] `EvaluatorRegistry.find_metric(name)` — find metric by name across all evaluator types
- [x] Upfront validation: resolve all metrics + check required fields before execution, 422 on failure
- [x] Error isolation: individual metric LLM errors do not affect other metrics

### 8. DB Schema Cleanup
- [x] PK rename: `evaluation_result.id` → `eval_id`, `llm_metadata.id` → `metadata_id`
- [x] Added `task_id` column to `evaluation_result` (nullable, indexed)
- [x] FK updated: `llm_metadata.evaluation_result_id` references `evaluation_result.eval_id`

### 9. Project Cleanup
- [x] Removed `migrations/` directory — will regenerate after schema stabilizes
- [x] Removed `alembic.ini`, `pyproject.toml`, `app/models/request.py`
- [x] Removed outdated docs: `docs/API_Documentation.md`, `docs/metrics-architecture-design.md`, `docs/evaluation_layer_spec.docx`
- [x] Removed empty `tests/unit/` directory
- [x] Added `.pytest_cache/` to `.gitignore`
- [x] Translated all Chinese to English across codebase (docs, API examples, comments, Field descriptions)

### 10. Documentation
- [x] `README.md` — full architecture, API reference, DB schema, data flow diagram
- [x] `docs/GETTING_STARTED.md` — local setup guide for onboarding
- [x] `app/evaluators/llm_judge/README.md` — registry mechanics, LLM config, how to add new metric
- [x] `app/db/README.md` — DB backend setup

---

## Current Table Schema

```
evaluation_result:
  eval_id(PK), task_id, metric_type, metric_name, status,
  score, reason(JSON), error_type, error_message,
  eval_latency_s, evaluated_at

llm_metadata:
  metadata_id(PK), evaluation_result_id(FK), judge_model,
  messages(JSON), raw_response(JSON),
  input_tokens, output_tokens, llm_latency_s, attempt_number
```

---

## Remaining

### Tests
- [ ] Independent unit tests per metric
- [ ] Registry registration and validation tests
- [ ] Batch endpoint integration tests
