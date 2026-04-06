# Evaluation Service

LLM evaluation metric calculation service. Provides two API types: single-metric endpoints (Swagger-friendly) and a batch concurrent endpoint.

## Architecture

```
API Layer (Routes / Persistence) → Registry Layer (Discovery / Validation) → Metrics Layer (Pure Evaluation Logic)
```

Three layers with one-way dependencies — no backward references:

- **Metrics Layer**: Each metric is a standalone plain class with no base class inheritance, depending only on `call_llm`. It defines its own `required_fields`, `request_model`, and returns `{"score", "reason"}`
- **Registry Layer**: Two-level routing — `EvaluatorRegistry` (dispatches by evaluator_type) → `MetricRegistry` (looks up by name). Duck-typing validation; auto-registers on import
- **API Layer**: Single-metric routes (dynamically registered at startup) + batch route (`asyncio.gather` concurrency). Handles HTTP protocol, per-request LLM config override (`ContextVar`), LLM call tracking, timing, and background persistence

### Data Flow

```
Single-metric request                      Batch request
POST /llm_judge/faithfulness               POST /batch
       │                                         │
       ▼                                         ▼
  _build_handler()                         batch_evaluate()
       │                                   ┌─┴─┴─┐
       ▼                                   │      │
  _evaluate_single()                   _evaluate_single() ×N (asyncio.gather concurrent)
       │                                   │      │
       ├─ resolve metric                    ├─ extract fields from test_case
       ├─ start_tracking()                  ├─ resolve metric
       ├─ set_config_override()             ├─ start_tracking() (each with independent ContextVar)
       ├─ metric.evaluate()                 ├─ set_config_override()
       ├─ get_tracked_calls()               ├─ metric.evaluate()
       └─ persist (background)              └─ persist (background)
```

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env         # fill in Azure OpenAI config
python -m app.db             # initial table creation (local mode only)
python main.py               # start the service → http://localhost:8000/docs
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_OPENAI_API_KEY` | Yes | | Azure OpenAI API Key |
| `AZURE_OPENAI_ENDPOINT` | Yes | | Azure OpenAI Endpoint |
| `AZURE_OPENAI_API_VERSION` | No | `2025-01-01-preview` | API version |
| `LLM_MODEL` | No | `gpt-4.1` | Model deployment name |
| `LLM_TEMPERATURE` | No | `0.0` | Generation temperature |
| `LLM_MAX_ATTEMPTS` | No | `3` | Max LLM call retry attempts (including first) |
| `DB_BACKEND` | No | `local` | Database backend (`local` / `azure`) |
| `SQLITE_DB_PATH` | No | `data/evaluation.db` | SQLite path (local mode only) |
| `LOG_LEVEL` | No | `INFO` | Log level |

## Project Structure

```
evaluation-service/
├── main.py                                  # Entry point, FastAPI + uvicorn
├── app/
│   ├── api/v1/evaluate.py                   # Routes: single-metric dynamic routes + /batch + /health
│   ├── evaluators/
│   │   ├── registry.py                      # EvaluatorRegistry + MetricRegistry + find_metric()
│   │   ├── __init__.py                      # Register evaluator types to top-level
│   │   ├── llm_judge/
│   │   │   ├── Faithfulness.py              # Faithfulness metric + FaithfulnessRequest
│   │   │   ├── FactualCorrectness.py        # Factual Correctness metric + FactualCorrectnessRequest
│   │   │   ├── registry.py                  # llm_judge sub-registry
│   │   │   └── __init__.py                  # Register metrics (auto-register on import)
│   │   └── performance/                     # Placeholder for formula-based metrics
│   ├── models/
│   │   ├── request.py                       # LLMConfig / BatchEvaluateRequest / ValidationErrorDetail
│   │   └── response.py                      # EvaluateResponse / Batch* / ErrorResponse
│   ├── db/
│   │   ├── models.py                        # SQLAlchemy ORM (EvaluationResult, LLMMetadata)
│   │   ├── connection.py                    # Async engine + session factory
│   │   ├── init_db.py                       # python -m app.db table creation entry point
│   │   ├── evaluation_result_repo.py        # upsert evaluation_result
│   │   └── llm_metadata_repo.py             # insert llm_metadata
│   ├── tasks/
│   │   └── persist.py                       # Background write for evaluation_result + llm_metadata
│   └── utils/
│       ├── config.py                        # DBSettings / LLMSettings / AppSettings
│       ├── constants.py                     # PROJECT_ROOT, PROMPT_DIR, DEFAULT_DB_PATH
│       ├── llm_utils.py                     # get_llm_client() + call_llm() (built-in retry)
│       ├── llm_tracker.py                   # ContextVar for LLM call tracking + per-request config override
│       └── logger.py                        # get_logger()
├── resource/prompt/prompt.yaml              # LLM prompt templates
├── tests/
│   └── integration/test_evaluate_api.py     # Integration tests
└── docs/task.md                             # Refactoring progress tracking
```

## API

### Health Check

```
GET /api/v1/evaluation/health
```

```json
{
  "status": "ok",
  "evaluators": {
    "llm_judge": ["faithfulness", "factual_correctness"],
    "performance": []
  },
  "version": "2.0.0"
}
```

### Single-Metric Endpoints

Each registered metric auto-generates a dedicated route:

```
POST /api/v1/evaluation/{evaluator_type}/{metric_name}
```

Currently available:

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/evaluation/llm_judge/faithfulness` | Faithfulness evaluation |
| `POST /api/v1/evaluation/llm_judge/factual_correctness` | Factual Correctness evaluation |

#### Faithfulness

Verifies whether the model answer is faithful to the retrieved context without hallucination.

**Request**

```json
{
  "response": "Gradient descent is an optimization algorithm",
  "retrieved_contexts": "Gradient Descent is an optimization algorithm used to minimize loss functions",
  "user_input": "Please explain gradient descent"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `response` | Yes | Model-generated answer |
| `retrieved_contexts` | Yes | Retrieved context |
| `user_input` | No | Original user question |
| `eval_id` | No | Evaluation ID, auto-generated UUID if not provided |
| `llm_config` | No | Per-request LLM config override (`model`, `temperature`) |

#### FactualCorrectness

Calculates precision / recall / F1 of the answer against the reference via claim decomposition and bidirectional NLI verification.

**Request**

```json
{
  "reference": "Domestic and imported hepatitis B vaccines are identical in safety and efficacy",
  "response": "There is no difference in safety between domestic and imported hepatitis B vaccines"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `reference` | Yes | Ground truth reference |
| `response` | Yes | Model-generated answer |
| `eval_id` | No | Evaluation ID, auto-generated UUID if not provided |
| `llm_config` | No | Per-request LLM config override (`model`, `temperature`) |

### Batch Endpoint

Evaluate multiple metrics in a single request; all metrics execute concurrently (`asyncio.gather`).

```
POST /api/v1/evaluation/batch
```

**Request**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "metrics": ["faithfulness", "factual_correctness"],
  "test_case": {
    "response": "There is no difference in safety between domestic and imported hepatitis B vaccines",
    "retrieved_contexts": "Domestic and imported hepatitis B vaccines are identical in safety and efficacy",
    "reference": "Domestic and imported hepatitis B vaccines are identical in safety and efficacy",
    "user_input": "Please explain the difference between domestic and imported hepatitis B vaccines"
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `metrics` | Yes | List of metric names to evaluate, at least 1 |
| `test_case` | Yes | Loose dict containing fields that any metric might need. Each metric automatically extracts only the fields it requires |
| `task_id` | No | Task ID shared across all metrics in the batch, auto-generated UUID if not provided |
| `llm_config` | No | Per-request LLM config override, applies to all metrics in the batch (`model`, `temperature`) |

**Response**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "results": [
    {
      "eval_id": "a1b2c3d4-...",
      "metric_name": "faithfulness",
      "status": "success",
      "result": { "score": 1.0, "reason": [...] },
      "metadata": {
        "evaluator_type": "llm_judge",
        "metric_name": "faithfulness",
        "eval_latency_s": 5.047,
        "evaluated_at": "2026-04-05T14:24:59.295911Z"
      }
    },
    {
      "eval_id": "e5f6a7b8-...",
      "metric_name": "factual_correctness",
      "status": "success",
      "result": { "score": 0.86, "reason": {...} },
      "metadata": {
        "evaluator_type": "llm_judge",
        "metric_name": "factual_correctness",
        "eval_latency_s": 17.531,
        "evaluated_at": "2026-04-05T14:24:59.295911Z"
      }
    }
  ]
}
```

Each metric result is independent: a failure in one metric does not affect others. Failed entries include `error` and `message` fields.

### Response Format (Single Metric)

```json
{
  "eval_id": "54540f73-c2e7-4b69-9a0f-7b241282cda2",
  "status": "success",
  "result": {
    "score": 1.0,
    "reason": [...]
  },
  "metadata": {
    "evaluator_type": "llm_judge",
    "metric_name": "faithfulness",
    "eval_latency_s": 5.047,
    "evaluated_at": "2026-04-05T14:24:59.295911Z"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `result.score` | `float` | Evaluation score (0.0 ~ 1.0) |
| `result.reason` | `any` | Evaluation details, structure varies by metric |
| `metadata.eval_latency_s` | `float` | Total evaluation latency (seconds) |

### Error Responses

| HTTP | error | Description |
|------|-------|-------------|
| 422 | Pydantic validation | Missing required fields or type errors |
| 422 | `VALIDATION_ERROR` | Unknown metrics or missing fields in batch request |
| 422 | `UNKNOWN_METRIC` | Metric not registered |
| 500 | `LLM_AUTH_ERROR` | Azure OpenAI authentication failed |
| 500 | `LLM_BAD_REQUEST` | Bad request parameters to LLM |
| 500 | `METRIC_ERROR` | Metric internal logic error |
| 503 | `LLM_RATE_LIMIT` | LLM rate limit exceeded |
| 504 | `LLM_TIMEOUT` | LLM request timeout |
| 500 | `INTERNAL_ERROR` | Unexpected internal error |

```json
{
  "detail": {
    "error": "ERROR_CODE",
    "message": "Human-readable description",
    "eval_id": "uuid"
  }
}
```

## Database

Two tables, written asynchronously in the background. Write failures do not affect HTTP responses.

### evaluation_result

| Column | Type | Description |
|--------|------|-------------|
| `eval_id` | VARCHAR(36) PK | Evaluation ID |
| `task_id` | VARCHAR(36) | Batch task ID (shared in batch requests, empty for single-metric requests) |
| `metric_type` | VARCHAR(64) | Evaluator type, e.g. `llm_judge` |
| `metric_name` | VARCHAR(64) | Metric name, e.g. `faithfulness` |
| `status` | VARCHAR(16) | `success` / `failed` |
| `score` | FLOAT | Evaluation score |
| `reason` | JSON | Evaluation details |
| `error_type` | VARCHAR(64) | Error type on failure |
| `error_message` | TEXT | Error description on failure |
| `eval_latency_s` | FLOAT | Total evaluation latency (seconds) |
| `evaluated_at` | TIMESTAMPTZ | Evaluation completion time |

### llm_metadata

| Column | Type | Description |
|--------|------|-------------|
| `metadata_id` | VARCHAR(36) PK | Auto-generated UUID |
| `evaluation_result_id` | VARCHAR(36) FK | References evaluation_result.eval_id |
| `judge_model` | VARCHAR(128) | Model used |
| `messages` | JSON | Full conversation messages `[{role, content}]` |
| `raw_response` | JSON | Raw LLM response `{content, model, finish_reason}` |
| `input_tokens` | INTEGER | Input token count |
| `output_tokens` | INTEGER | Output token count |
| `llm_latency_s` | FLOAT | Single LLM call latency (seconds) |
| `attempt_number` | SMALLINT | Attempt number |

### LLM Call Tracking

Each evaluation automatically tracks all LLM calls via `ContextVar`:

1. `_evaluate_single` calls `start_tracking()` to initialize
2. `call_llm()` automatically calls `record_call()` on each invocation
3. After evaluation, `get_tracked_calls()` retrieves all records
4. Background task commits evaluation_result + all llm_metadata in one transaction

In batch mode, each metric runs in an independent task within `asyncio.gather`, each with its own `ContextVar` copy — no cross-contamination.

### LLM Config Override

Both single-metric and batch endpoints accept an optional `llm_config` field to override model settings per-request:

```json
{
  "llm_config": {
    "model": "gpt-4.1",
    "temperature": 0.3
  }
}
```

Priority: **API param** > **env var** (`LLM_MODEL` / `LLM_TEMPERATURE`) > **default**

The override is injected transparently via `ContextVar` (`set_config_override` / `get_config_override`) — metric code is unaware of it. Each concurrent metric in a batch gets its own isolated config copy.

## Adding a New Metric

1. Create a file under `app/evaluators/llm_judge/`:

```python
from typing import Optional
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from app.utils.llm_utils import call_llm
from app.models.request import LLMConfig

class MyMetricRequest(BaseModel):
    eval_id: UUID = Field(default_factory=uuid4)
    input_text: str = Field(..., description="Input text")
    llm_config: Optional[LLMConfig] = Field(None, description="Per-request LLM config override")

class MyMetric:
    name: str = "my_metric"
    required_fields: list[str] = ["input_text"]
    optional_fields: list[str] = []       # optional
    request_model = MyMetricRequest

    async def evaluate(self, input_text: str) -> dict:
        return {"score": 1.0, "reason": "looks good"}
```

2. Register in `app/evaluators/llm_judge/__init__.py`:

```python
llm_judge_registry.register(MyMetric())
```

After restarting the service, the following are auto-generated:
- Single-metric route: `POST /api/v1/evaluation/llm_judge/my_metric`
- Can also be called via the batch endpoint: `"metrics": ["my_metric"]`

## Retry Mechanism

`call_llm` has built-in exponential backoff retry:

| Exception | Retry |
|-----------|-------|
| `RateLimitError (429)` | Yes |
| `APITimeoutError` | Yes |
| `APIStatusError (503)` | Yes |
| `AuthenticationError` | No |
| `BadRequestError (400)` | No |

Backoff formula: `min(base_wait^attempt, max_wait) ± jitter`

## Adding a New Evaluator Type

To add non-LLM metrics (e.g. formula-based), create a new sub-package:

1. `app/evaluators/performance/` — directory already reserved
2. Create metric classes (same as above), create a sub-registry in `registry.py`
3. Register metrics in `__init__.py`
4. Register the new type in `app/evaluators/__init__.py`:

```python
evaluator_registry.register_type("performance", performance_registry)
```
