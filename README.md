# Evaluation Service

LLM 评估指标计算服务。每个评估指标对应一条独立 REST 端点，请求体按指标字段强类型校验。

## 架构

```
API 层（路由/存储） → Registry 层（发现/校验） → Metrics 层（纯评估逻辑）
```

- **Metrics 层**：每个 metric 是独立类，不继承基类，只依赖 `call_llm`
- **Registry 层**：两级路由 — `EvaluatorRegistry`（按 type 分发）→ `MetricRegistry`（按 name 查找）
- **API 层**：启动时遍历 registry 动态注册路由，负责 HTTP 协议、计时、持久化

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env       # 填写 Azure OpenAI 配置
python main.py             # 启动服务 → http://localhost:8000/docs
```

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `AZURE_OPENAI_API_KEY` | 是 | | Azure OpenAI API Key |
| `AZURE_OPENAI_ENDPOINT` | 是 | | Azure OpenAI Endpoint |
| `AZURE_OPENAI_API_VERSION` | 否 | `2025-01-01-preview` | API 版本 |
| `LLM_MODEL` | 否 | `gpt-4.1` | 模型部署名 |
| `LLM_TEMPERATURE` | 否 | `0.0` | 生成温度 |
| `LLM_MAX_ATTEMPTS` | 否 | `3` | 最大重试次数 |
| `DB_BACKEND` | 否 | `local` | 数据库后端（`local` / `azure`） |
| `SQLITE_DB_PATH` | 否 | `data/evaluation.db` | SQLite 数据库路径 |

## 项目结构

```
evaluation-service/
├── main.py                              # 入口，uvicorn 启动
├── app/
│   ├── api/v1/evaluate.py               # 动态路由注册 + 核心处理逻辑
│   ├── evaluators/
│   │   ├── registry.py                  # EvaluatorRegistry + MetricRegistry
│   │   ├── __init__.py                  # 注册 evaluator type
│   │   ├── llm_judge/
│   │   │   ├── Faithfulness.py          # 忠实度 metric + RequestModel
│   │   │   ├── FactualCorrectness.py    # 事实正确性 metric + RequestModel
│   │   │   ├── registry.py              # llm_judge 子 registry
│   │   │   └── __init__.py              # 注册 metrics
│   │   └── performance/                 # 预留，公式类 metric
│   ├── models/
│   │   ├── request.py                   # 基础请求模型
│   │   └── response.py                  # EvaluateResponse / MetricResult / ErrorResponse
│   ├── db/                              # 数据持久化
│   ├── tasks/persist.py                 # 后台写入 eval_log
│   └── utils/                           # config、logger、llm_utils
├── migrations/                          # Alembic 数据库迁移
└── tests/
    └── integration/test_evaluate_api.py # 集成测试（7/7）
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

### 评估指标端点

每个注册的 metric 自动生成一条独立路由：

```
POST /api/v1/evaluation/{evaluator_type}/{metric_name}
```

当前可用：

| 端点 | 说明 |
|------|------|
| `POST /api/v1/evaluation/llm_judge/faithfulness` | 忠实度评估 |
| `POST /api/v1/evaluation/llm_judge/factual_correctness` | 事实正确性评估 |

### Faithfulness — 忠实度

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
| `eval_id` | 否 | 评估 ID，不传自动生成 |

### FactualCorrectness — 事实正确性

通过 claim 分解和 NLI 验证，计算回答相对参考答案的 precision / recall / F1。

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
| `eval_id` | 否 | 评估 ID，不传自动生成 |

### 响应格式

```json
{
  "eval_id": "54540f73-c2e7-4b69-9a0f-7b241282cda2",
  "status": "success",
  "result": {
    "score": 1.0,
    "reason": [
      {
        "statement": "梯度下降是一种优化算法。",
        "reason": "上下文明确指出梯度下降是一种用于最小化损失函数的优化算法",
        "verdict": 1
      }
    ]
  },
  "metadata": {
    "evaluator_type": "llm_judge",
    "metric_name": "faithfulness",
    "eval_latency_ms": 5047,
    "evaluated_at": "2026-04-04T14:24:59.295911Z"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `result.score` | `float` | 评估分数（0.0 ~ 1.0） |
| `result.reason` | `any` | 评估详情，结构因 metric 而异 |
| `metadata` | `object` | 运行上下文（类型、名称、耗时、时间） |

### 错误响应

| HTTP | error | 说明 |
|------|-------|------|
| 422 | Pydantic 校验 | 缺少必填字段或类型错误 |
| 422 | `UNKNOWN_METRIC` | metric 未注册 |
| 500 | `LLM_AUTH_ERROR` | Azure OpenAI 认证失败 |
| 500 | `LLM_BAD_REQUEST` | LLM 请求参数错误 |
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

## 添加新 Metric

1. 在 `app/evaluators/llm_judge/` 下创建文件，定义 metric 类和 request model：

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
    request_model = MyMetricRequest

    async def evaluate(self, input_text: str) -> dict:
        return {"score": 1.0, "reason": "looks good"}
```

2. 在 `app/evaluators/llm_judge/__init__.py` 注册：

```python
llm_judge_registry.register(MyMetric())
```

重启服务后自动生成 `POST /api/v1/evaluation/llm_judge/my_metric` 路由。

## 重试机制

`call_llm` 内置指数退避重试：

| 异常 | 重试 |
|------|------|
| `RateLimitError (429)` | 是 |
| `APITimeoutError` | 是 |
| `APIStatusError (503)` | 是 |
| `AuthenticationError` | 否 |
| `BadRequestError (400)` | 否 |
