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
- [x] Migration 0001/0002 synced

### 7. Current Table Schema
```
evaluation_result:
  id(PK), metric_type, metric_name, status,
  score, reason(JSON), error_type, error_message,
  eval_latency_s, evaluated_at

llm_metadata:
  id(PK), evaluation_result_id(FK), judge_model,
  messages(JSON), raw_response(JSON),
  input_tokens, output_tokens, llm_latency_s, attempt_number
```

### 8. Git commits on branch `refactor/metrics-decoupling`
- `0da923f` — utils package + metrics layer rewrite
- `b35a061` — MetricRegistry + duck typing validation
- `3ae6833` — restructured into type-based packages
- `120aaa7` — API layer refactoring (per-metric routes)
- `13f2701` — old file cleanup
- `68cb0b3` — response format refactoring + eval_id optional + README
- `1a48f34` — latency changed from ms to seconds
- `c892aa4` — config consolidation + DB table/field refactoring
- `7fb4eab` — LLM tracking (ContextVar) + persist llm_metadata + DB path as constant

---

## Remaining

### 9. Batch API (Scheduler Layer Unified Entry Point)
- [x] Added `POST /api/v1/evaluation/batch`
- [x] Request model:
  ```json
  {
    "task_id": "uuid (optional)",
    "metrics": ["faithfulness", "factual_correctness"],
    "test_case": { "response": "...", "retrieved_contexts": "...", "reference": "...", ... }
  }
  ```
- [x] Internal logic: iterate metrics → extract fields from test_case → validate with required_fields → call evaluate
- [x] Concurrent execution: `asyncio.gather` runs multiple metrics concurrently (not serially)
- [x] DB change: `evaluation_result` added `task_id` column (optional, shared across metrics under same task)
- [x] Keep existing per-metric routes (single user / Swagger)
- [x] Both route types share `_evaluate_single()` core logic
- [x] `EvaluatorRegistry.find_metric(name)` — find metric by name across types
- [x] Migration 0003 — added task_id column + index

### 10. Old File Cleanup
- [ ] `app/evaluators/base.py` — to be deleted
- [ ] `tests/unit/` — old tests need rewriting

### 11. Tests
- [ ] Independent unit tests per metric
- [ ] Registry registration and validation tests
- [ ] Batch endpoint integration tests
