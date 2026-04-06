# LLM Judge Evaluator

## Architecture

```
API Layer (routing/storage) → Registry Layer (discovery/validation) → Metrics Layer (pure evaluation logic)
```

Three-layer separation of concerns. Metrics have no business-layer dependencies — they only use `call_llm`.

## File Structure

```
app/evaluators/
├── __init__.py                 # Register all evaluator types to top-level registry
├── registry.py                 # EvaluatorRegistry top-level router
├── llm_judge/                  # LLM Judge class
│   ├── __init__.py             # Import triggers auto-registration of all LLM-judge metrics
│   ├── registry.py             # LLMJudgeRegistry sub-registry
│   ├── Faithfulness.py         # Metric implementation
│   ├── FactualCorrectness.py   # Metric implementation
│   └── README.md
├── performance/                # Formula-based (future extension)
│   └── ...
```

## How to Register a New Metric

### 1. Create the Metric Class

Create a new file under `app/evaluators/llm_judge/`, implement a plain class with the following attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Globally unique identifier, used for registry lookup and API routing |
| `required_fields` | `list[str]` | Required fields for evaluate, used by registry for input validation |
| `optional_fields` | `list[str]` | Optional fields (can be omitted, defaults to empty list) |
| `evaluate` | `async def` | Unified evaluation entry point, accepts keyword arguments, returns dict |

```python
class MyMetric:
    name: str = "my_metric"
    required_fields: list[str] = ["response", "reference"]
    optional_fields: list[str] = ["context"]  # optional

    async def evaluate(self, response: str, reference: str, context: str | None = None) -> dict:
        # ... call call_llm for evaluation ...
        return {"score": 0.9, "reason": "..."}
```

Constraints:
- No base class inheritance, no registry references
- Internally calls LLM via `from app.utils.llm_utils import call_llm`
- Prompt templates are defined in `resource/prompt/prompt.yaml`

### 2. Register to Sub-Registry

Import and register in `llm_judge/__init__.py`:

```python
from app.evaluators.llm_judge.MyMetric import MyMetric
from app.evaluators.llm_judge.registry import llm_judge_registry

llm_judge_registry.register(MyMetric())
```

`register()` performs duck-typing check for `name`, `required_fields`, `evaluate` — raises `TypeError` if missing.

### 3. Register a New Evaluator Type (Future Extension)

```python
# app/evaluators/__init__.py
from app.evaluators.performance import performance_registry
evaluator_registry.register_type("performance", performance_registry)
```

Top-level `EvaluatorRegistry` handles automatic routing — no changes to existing code needed.

## Registry Mechanics

### Top-level EvaluatorRegistry (`app/evaluators/registry.py`)

Global singleton `evaluator_registry`, routes by evaluator type to sub-registries:

| Method | Description |
|--------|-------------|
| `register_type(type, sub_registry)` | Register an evaluator type |
| `get(type, name)` | Get metric instance by type + name |
| `validate_record(type, name, record)` | Validate record fields |
| `list_types()` | Return all registered evaluator types |
| `list_metrics(type)` | Return all metric names under a type |

Typical call flow (API layer):

```python
evaluator_registry.validate_record("llm_judge", "faithfulness", record)
metric = evaluator_registry.get("llm_judge", "faithfulness")
result = await metric.evaluate(**record)
```

### LLM Judge Sub-Registry (`app/evaluators/llm_judge/registry.py`)

| Method | Description |
|--------|-------------|
| `register(metric)` | Register metric with duck-typing validation |
| `get(name)` | Get metric, raises `KeyError` if not registered |
| `validate_record(name, record)` | Validate required_fields, raises `ValueError` if fields missing |
| `list_metrics()` | Return all registered metric names |

## Prompt Templates

All prompts are defined in `resource/prompt/prompt.yaml`, referenced via `PROMPT_DIR` in `app/utils/constants.py`. To modify prompts, just edit the yaml file — no code changes needed.

## LLM Configuration

All LLM calls go through `call_llm()` (`app/utils/llm_utils.py`) with built-in retry and error classification:

- **Non-retryable errors**: missing env vars (`ValueError`), auth failure, bad request → raised immediately
- **Retryable errors**: timeout, rate limit, 503 → exponential backoff retry

### Environment Variables

All LLM client configuration is managed via environment variables, defined in the `LLMSettings` class in `app/utils/config.py`.

#### Required

Must be set in `.env` or system env vars before startup:

| Environment Variable | Description |
|---------------------|-------------|
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API Key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI Endpoint URL |

If not set, `call_llm()` raises `ValueError` when called.

#### Optional (has defaults)

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AZURE_OPENAI_API_VERSION` | `2025-01-01-preview` | Azure OpenAI API version |
| `LLM_MODEL` | `gpt-4.1` | Model name |
| `LLM_TEMPERATURE` | `0.0` | Generation temperature |
| `LLM_MAX_ATTEMPTS` | `3` | Max retry attempts |
| `LLM_BASE_WAIT` | `2.0` | Exponential backoff base wait time (seconds) |
| `LLM_MAX_WAIT` | `10.0` | Max wait time (seconds) |
| `LLM_JITTER` | `0.5` | Random jitter range (seconds) |

#### Configuration Loading Flow

```
.env / System environment variables
       ↓  pydantic_settings auto-loaded by
LLMSettings (app/utils/config.py)
       ↓  llm_settings singleton
get_llm_client() / call_llm() (app/utils/llm_utils.py)
```

1. `LLMSettings` inherits `BaseSettings`, auto-loads from `.env` file and env vars at startup
2. Global singleton `llm_settings` is created in `app/utils/config.py`
3. `get_llm_client()` reads key/endpoint from `llm_settings` to create `AsyncAzureOpenAI`
4. `call_llm()` reads model/temperature/retry params from `llm_settings` to execute calls

#### Modifying Configuration

- **Change defaults**: directly edit `LLMSettings` field defaults in `app/utils/config.py`
- **Runtime override**: set the corresponding env var in `.env` to override defaults — no code changes needed

#### Quick Test

```bash
# Run from project root
python -m app.utils.llm_utils
```

Prints all current config and sends a test request via `call_llm()` to verify connectivity.
