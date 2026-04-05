# Evaluation Service

LLM 评估指标计算服务。提供两类 API：单指标端点（Swagger 友好）和批量并发端点。

## 架构

```
API 层（路由/存储） → Registry 层（发现/校验） → Metrics 层（纯评估逻辑）
```

三层单向依赖，不可反向：

- **Metrics 层**：每个 metric 是独立朴素类，不继承基类，只依赖 `call_llm`。定义自己的 `required_fields`、`request_model`，返回 `{"score", "reason"}`
- **Registry 层**：两级路由 — `EvaluatorRegistry`（按 evaluator_type 分发）→ `MetricRegistry`（按 name 查找）。Duck typing 校验，import 即注册
- **API 层**：单指标路由（启动时动态注册）+ 批量路由（`asyncio.gather` 并发）。负责 HTTP 协议、LLM 调用追踪、计时、后台持久化

### 数据流

```
单指标请求                           批量请求
POST /llm_judge/faithfulness        POST /batch
       │                                  │
       ▼                                  ▼
  _build_handler()                  batch_evaluate()
       │                            ┌─┴─┴─┐
       ▼                            │      │
  _evaluate_single()            _evaluate_single() ×N (asyncio.gather 并发)
       │                            │      │
       ├─ resolve metric             ├─ 从 test_case 提取字段
       ├─ start_tracking()           ├─ resolve metric
       ├─ metric.evaluate()          ├─ start_tracking() (各独立 ContextVar)
       ├─ get_tracked_calls()        ├─ metric.evaluate()
       └─ persist (background)       └─ persist (background)
```

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env         # 填写 Azure OpenAI 配置
python -m app.db             # 首次建表（仅 local 模式需要）
python main.py               # 启动服务 → http://localhost:8000/docs
```

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `AZURE_OPENAI_API_KEY` | 是 | | Azure OpenAI API Key |
| `AZURE_OPENAI_ENDPOINT` | 是 | | Azure OpenAI Endpoint |
| `AZURE_OPENAI_API_VERSION` | 否 | `2025-01-01-preview` | API 版本 |
| `LLM_MODEL` | 否 | `gpt-4.1` | 模型部署名 |
| `LLM_TEMPERATURE` | 否 | `0.0` | 生成温度 |
| `LLM_MAX_ATTEMPTS` | 否 | `3` | LLM 调用最大重试次数（含首次） |
| `DB_BACKEND` | 否 | `local` | 数据库后端（`local` / `azure`） |
| `SQLITE_DB_PATH` | 否 | `data/evaluation.db` | SQLite 路径（仅 local 模式） |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |

## 项目结构

```
evaluation-service/
├── main.py                                  # 入口，FastAPI + uvicorn
├── app/
│   ├── api/v1/evaluate.py                   # 路由：单指标动态路由 + /batch + /health
│   ├── evaluators/
│   │   ├── registry.py                      # EvaluatorRegistry + MetricRegistry + find_metric()
│   │   ├── __init__.py                      # 注册 evaluator type 到顶层
│   │   ├── llm_judge/
│   │   │   ├── Faithfulness.py              # 忠实度 metric + FaithfulnessRequest
│   │   │   ├── FactualCorrectness.py        # 事实正确性 metric + FactualCorrectnessRequest
│   │   │   ├── registry.py                  # llm_judge 子 registry
│   │   │   └── __init__.py                  # 注册 metrics（import 即注册）
│   │   └── performance/                     # 预留，公式类 metric
│   ├── models/
│   │   └── response.py                      # EvaluateResponse / Batch* / ErrorResponse
│   ├── db/
│   │   ├── models.py                        # SQLAlchemy ORM（EvaluationResult, LLMMetadata）
│   │   ├── connection.py                    # 异步引擎 + session 工厂
│   │   ├── init_db.py                       # python -m app.db 建表入口
│   │   ├── evaluation_result_repo.py        # upsert evaluation_result
│   │   └── llm_metadata_repo.py             # insert llm_metadata
│   ├── tasks/
│   │   └── persist.py                       # 后台写入 evaluation_result + llm_metadata
│   └── utils/
│       ├── config.py                        # DBSettings / LLMSettings / AppSettings
│       ├── constants.py                     # PROJECT_ROOT, PROMPT_DIR, DEFAULT_DB_PATH
│       ├── llm_utils.py                     # get_llm_client() + call_llm()（内置重试）
│       ├── llm_tracker.py                   # ContextVar 追踪 LLM 调用元数据
│       └── logger.py                        # get_logger()
├── resource/prompt/prompt.yaml              # LLM prompt 模板
├── tests/
│   └── integration/test_evaluate_api.py     # 集成测试
└── docs/task.md                             # 重构进度追踪
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

### 单指标端点

每个注册的 metric 自动生成一条独立路由：

```
POST /api/v1/evaluation/{evaluator_type}/{metric_name}
```

当前可用：

| 端点 | 说明 |
|------|------|
| `POST /api/v1/evaluation/llm_judge/faithfulness` | 忠实度评估 |
| `POST /api/v1/evaluation/llm_judge/factual_correctness` | 事实正确性评估 |

#### Faithfulness — 忠实度

验证模型回答是否忠实于检索上下文，不臆造内容。

**Request**

```json
{
  "response": "梯度下降是一种优化算法",
  "retrieved_contexts": "梯度下降（Gradient Descent）是一种用于最小化损失函数的优化算法",
  "user_input": "请解释梯度下降"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `response` | 是 | 模型生成的回答 |
| `retrieved_contexts` | 是 | 检索到的上下文 |
| `user_input` | 否 | 用户的原始提问 |
| `eval_id` | 否 | 评估 ID，不传自动生成 UUID |

#### FactualCorrectness — 事实正确性

通过 claim 分解和 NLI 双向验证，计算回答相对参考答案的 precision / recall / F1。

**Request**

```json
{
  "reference": "国产乙肝疫苗与进口乙肝疫苗在安全性和预防效果上完全相同",
  "response": "国产乙肝疫苗与进口疫苗在安全性方面没有区别"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `reference` | 是 | 标准参考答案 |
| `response` | 是 | 模型生成的回答 |
| `eval_id` | 否 | 评估 ID，不传自动生成 UUID |

### 批量端点

一次请求评估多个指标，所有指标并发执行（`asyncio.gather`）。

```
POST /api/v1/evaluation/batch
```

**Request**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "metrics": ["faithfulness", "factual_correctness"],
  "test_case": {
    "response": "国产乙肝疫苗与进口疫苗在安全性方面没有区别",
    "retrieved_contexts": "国产乙肝疫苗与进口乙肝疫苗在安全性和预防效果上完全相同",
    "reference": "国产乙肝疫苗与进口乙肝疫苗在安全性和预防效果上完全相同",
    "user_input": "请解释国产和进口乙肝疫苗的区别"
  }
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `metrics` | 是 | 要评估的指标名称列表，至少 1 个 |
| `test_case` | 是 | 宽松 dict，包含所有指标可能需要的字段。每个指标自动从中提取自己需要的字段 |
| `task_id` | 否 | 任务 ID，同批次内所有指标共享，不传自动生成 UUID |

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

每个指标结果独立：某个指标失败不影响其他指标，失败的条目会包含 `error` 和 `message` 字段。

### 响应格式（单指标）

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `result.score` | `float` | 评估分数（0.0 ~ 1.0） |
| `result.reason` | `any` | 评估详情，结构因 metric 而异 |
| `metadata.eval_latency_s` | `float` | 评估总耗时（秒） |

### 错误响应

| HTTP | error | 说明 |
|------|-------|------|
| 422 | Pydantic 校验 | 缺少必填字段或类型错误 |
| 422 | `VALIDATION_ERROR` | 批量请求中存在未知指标或缺失字段 |
| 422 | `UNKNOWN_METRIC` | 指标未注册 |
| 500 | `LLM_AUTH_ERROR` | Azure OpenAI 认证失败 |
| 500 | `LLM_BAD_REQUEST` | LLM 请求参数错误 |
| 500 | `METRIC_ERROR` | 指标内部逻辑错误 |
| 503 | `LLM_RATE_LIMIT` | LLM 请求频率超限 |
| 504 | `LLM_TIMEOUT` | LLM 请求超时 |
| 500 | `INTERNAL_ERROR` | 未预期的内部错误 |

```json
{
  "detail": {
    "error": "ERROR_CODE",
    "message": "Human-readable description",
    "eval_id": "uuid"
  }
}
```

## 数据库

两张表，后台异步写入，写失败不影响 HTTP 响应。

### evaluation_result

| 列 | 类型 | 说明 |
|----|------|------|
| `eval_id` | VARCHAR(36) PK | 评估 ID |
| `task_id` | VARCHAR(36) | 批量任务 ID（批量请求共享，单指标请求为空） |
| `metric_type` | VARCHAR(64) | 评估器类型，如 `llm_judge` |
| `metric_name` | VARCHAR(64) | 指标名称，如 `faithfulness` |
| `status` | VARCHAR(16) | `success` / `failed` |
| `score` | FLOAT | 评估分数 |
| `reason` | JSON | 评估详情 |
| `error_type` | VARCHAR(64) | 失败时的错误类型 |
| `error_message` | TEXT | 失败时的错误描述 |
| `eval_latency_s` | FLOAT | 评估总耗时（秒） |
| `evaluated_at` | TIMESTAMPTZ | 评估完成时间 |

### llm_metadata

| 列 | 类型 | 说明 |
|----|------|------|
| `metadata_id` | VARCHAR(36) PK | 自生成 UUID |
| `evaluation_result_id` | VARCHAR(36) FK | 关联 evaluation_result.eval_id |
| `judge_model` | VARCHAR(128) | 使用的模型 |
| `messages` | JSON | 完整对话消息 `[{role, content}]` |
| `raw_response` | JSON | LLM 原始返回 `{content, model, finish_reason}` |
| `input_tokens` | INTEGER | 输入 token 数 |
| `output_tokens` | INTEGER | 输出 token 数 |
| `llm_latency_s` | FLOAT | 单次 LLM 调用耗时（秒） |
| `attempt_number` | SMALLINT | 第几次尝试 |

### LLM 调用追踪

每次评估通过 `ContextVar` 自动追踪所有 LLM 调用：

1. `_evaluate_single` 调用 `start_tracking()` 初始化
2. `call_llm()` 内部每次调用自动 `record_call()`
3. 评估结束后 `get_tracked_calls()` 取出全部记录
4. 后台任务将 evaluation_result + 所有 llm_metadata 一次 commit

批量模式下，`asyncio.gather` 内每个指标在独立 task 中运行，各自拥有独立的 `ContextVar` 副本，互不干扰。

## 添加新 Metric

1. 在 `app/evaluators/llm_judge/` 下创建文件：

```python
from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from app.utils.llm_utils import call_llm

class MyMetricRequest(BaseModel):
    eval_id: UUID = Field(default_factory=uuid4)
    input_text: str = Field(..., description="输入文本")

class MyMetric:
    name: str = "my_metric"
    required_fields: list[str] = ["input_text"]
    optional_fields: list[str] = []       # 可选
    request_model = MyMetricRequest

    async def evaluate(self, input_text: str) -> dict:
        return {"score": 1.0, "reason": "looks good"}
```

2. 在 `app/evaluators/llm_judge/__init__.py` 注册：

```python
llm_judge_registry.register(MyMetric())
```

重启服务后自动生成：
- 单指标路由：`POST /api/v1/evaluation/llm_judge/my_metric`
- 可通过批量端点调用：`"metrics": ["my_metric"]`

## 重试机制

`call_llm` 内置指数退避重试：

| 异常 | 重试 |
|------|------|
| `RateLimitError (429)` | 是 |
| `APITimeoutError` | 是 |
| `APIStatusError (503)` | 是 |
| `AuthenticationError` | 否 |
| `BadRequestError (400)` | 否 |

退避公式：`min(base_wait^attempt, max_wait) ± jitter`

## 添加新 Evaluator Type

如需添加非 LLM 类指标（如公式计算），创建新的子包：

1. `app/evaluators/performance/` — 已预留目录
2. 创建 metric 类（同上），在 `registry.py` 创建子 registry
3. `__init__.py` 中注册 metric
4. `app/evaluators/__init__.py` 注册新 type：

```python
evaluator_registry.register_type("performance", performance_registry)
```
