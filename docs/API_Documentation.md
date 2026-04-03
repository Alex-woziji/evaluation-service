# Evaluation Service

LLM 评估平台的指标计算层。职责单一：接收单条 record，执行指标计算，同步返回结果，后台异步写执行日志。

> **不感知** ETL、不感知调度、不感知中间表 ID 体系。

---

## 目录

- [快速开始](#快速开始)
- [架构说明](#架构说明)
- [API](#api)
- [请求校验](#请求校验)
- [Evaluator 开发指南](#evaluator-开发指南)
- [数据库](#数据库)
- [重试机制](#重试机制)
- [错误码](#错误码)
- [项目结构](#项目结构)

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 填写 DATABASE_URL、OPENAI_API_KEY 等

# 运行数据库迁移
alembic upgrade head

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 架构说明

```
调度层
  │  POST /evaluate（同步等待，含 LLM 调用耗时）
  ▼
Evaluation Service
  ├── 参数校验（Pydantic + validate_config）
  ├── EvaluatorRegistry.get(metric_type)
  ├── evaluator.evaluate(record, config)   ← 含内部重试
  ├── 返回 EvaluateResponse
  └── BackgroundTask: 写 eval_log + llm_call_log
```

**关键约定：**

- `eval_id` 由**调度层**生成并传入，Evaluation Service 不生成、不管理任务状态
- 调度层负责维护 `source_record_id → eval_id` 的映射关系
- 调度层通过 `asyncio.gather()` + `Semaphore` 控制并发，Service 本身无限流逻辑
- Background Task 写库失败不影响 Response，只打 ERROR 日志 + 告警

---

## API

### POST /api/v1/evaluation/evaluate

执行单条 record 的评估，**同步返回结果**。

**Request Body**

```json
{
  "eval_id": "550e8400-e29b-41d4-a716-446655440000",
  "metric_type": "llm_judge",
  "record": {
    "input": "请解释什么是梯度下降",
    "output": "梯度下降是一种优化算法...",
    "reference": "梯度下降（Gradient Descent）是..."
  },
  "eval_config": {
    "judge_model": "gpt-4o",
    "criteria": ["accuracy", "completeness", "clarity"],
    "rubric": "评估回答是否准确、完整地解释了核心概念"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `eval_id` | `string (UUID)` | ✅ | 调度层生成，用于幂等和日志关联 |
| `metric_type` | `string` | ✅ | 路由到对应 Evaluator，未注册返回 422 |
| `record.input` | `string` | ✅ | 模型原始输入 |
| `record.output` | `string` | ✅ | 待评估的模型输出 |
| `record.reference` | `string` | 视 metric 而定 | 参考答案，`llm_judge` 可选 |
| `record.metadata` | `object` | 否 | 扩展字段，性能指标等放此处 |
| `eval_config` | `object` | ✅ | 各 metric 的配置，字段要求见[请求校验](#请求校验) |

**Response 200**

```json
{
  "eval_id": "550e8400-e29b-41d4-a716-446655440000",
  "metric_type": "llm_judge",
  "status": "success",
  "score": 0.87,
  "scores_detail": {
    "accuracy": 0.90,
    "completeness": 0.85,
    "clarity": 0.85
  },
  "reasoning": "回答准确覆盖了核心机制，但缺少对学习率选择的讨论...",
  "raw_output": {},
  "retry_count": 0,
  "eval_latency_ms": 4312,
  "evaluated_at": "2025-04-03T10:23:45.123Z"
}
```

**Response 422** — 参数校验失败

```json
{
  "error": "VALIDATION_ERROR",
  "detail": [
    { "field": "eval_config.judge_model", "message": "field required" }
  ]
}
```

**Response 500** — Evaluator 执行失败

```json
{
  "error": "LLM_API_ERROR",
  "message": "Rate limit exceeded after 3 retries",
  "retry_count": 3,
  "eval_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### GET /api/v1/evaluation/health

```json
{
  "status": "ok",
  "registered_evaluators": ["llm_judge"],
  "version": "1.0.0"
}
```

---

## 请求校验

校验分两层，**顺序执行**，任意一层失败均返回 422。

### 第一层：通用字段校验（Pydantic）

所有请求共用，在路由层自动执行：

- `eval_id`：非空 UUID 格式
- `metric_type`：非空字符串，在已注册列表中
- `record.input`、`record.output`：非空字符串
- `eval_config`：非空 object

### 第二层：metric 级别校验（validate_config）

每个 Evaluator 在 `validate_config()` 中定义自己的必填字段，**在 evaluate() 执行前调用**。校验失败抛出 `ConfigValidationError`，触发 422。

**llm_judge 校验规则：**

| 字段 | 要求 |
|------|------|
| `eval_config.judge_model` | 必填，非空字符串 |
| `eval_config.criteria` | 必填，非空数组，每项为字符串 |
| `eval_config.rubric` | 可选，默认使用 Evaluator 内置 rubric |
| `eval_config.score_range` | 可选，默认 `{"min": 0, "max": 1}`，需满足 min < max |
| `eval_config.language` | 可选，默认 `"zh"` |

**新增 Evaluator 时**，在 `validate_config()` 中声明该 metric 的必填字段，框架会自动在执行前调用。无需修改路由或通用校验逻辑。

---

## Evaluator 开发指南

### 新增一个 Evaluator 的完整步骤

**第一步：实现类**

```python
# app/evaluators/my_evaluator.py

from app.evaluators.base import BaseEvaluator, EvalRecord, EvalConfig, EvalResult
from app.evaluators.registry import registry
from app.exceptions import ConfigValidationError

@registry.register
class MyEvaluator(BaseEvaluator):
    metric_type = "my_metric"   # 对应请求中的 metric_type 字段

    def validate_config(self, config: EvalConfig) -> None:
        # 声明该 metric 的必填字段，校验失败抛 ConfigValidationError
        if not config.extra.get("my_required_field"):
            raise ConfigValidationError("my_required_field is required for my_metric")

    async def evaluate(self, record: EvalRecord, config: EvalConfig) -> EvalResult:
        # 实现评估逻辑，含内部重试
        # 重试耗尽后抛出 EvaluationError
        ...
        return EvalResult(
            score=0.85,
            scores_detail={"dimension_a": 0.85},
            reasoning="...",
            raw_output={},
            retry_count=0,
            eval_latency_ms=1200,
        )
```

**第二步：触发注册**

```python
# app/evaluators/__init__.py
from app.evaluators import llm_judge_evaluator
from app.evaluators import my_evaluator   # 加这一行
```

**第三步：补充文档**

在本 README 的「已注册 Evaluator」章节追加说明。

---

### 数据模型参考

```python
@dataclass
class EvalRecord:
    input: str
    output: str
    reference: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class EvalConfig:
    judge_model: str = ""
    criteria: List[str] = field(default_factory=list)
    rubric: Optional[str] = None
    score_range: Dict[str, float] = field(default_factory=lambda: {"min": 0, "max": 1})
    language: str = "zh"
    extra: Dict[str, Any] = field(default_factory=dict)   # 各 metric 自定义参数放这里

@dataclass
class EvalResult:
    score: float
    scores_detail: Dict[str, float]
    retry_count: int
    eval_latency_ms: int
    reasoning: Optional[str] = None
    raw_output: Optional[Dict] = None
```

---

## 数据库

Service 维护两张**运维/溯源**用途的表，与业务结果表无关。

### eval_log

所有 metric_type 通用，Background Task 异步写入。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | 即 `eval_id`，由调度层传入 |
| `metric_type` | VARCHAR(64) | 指标类型 |
| `status` | VARCHAR(16) | `success` \| `failed` |
| `score` | FLOAT | 归一化总分，failed 时为 NULL |
| `scores_detail` | JSONB | 分项得分 |
| `reasoning` | TEXT | 评分理由 |
| `error_type` | VARCHAR(64) | 失败时的错误类型 |
| `error_message` | TEXT | 失败时的错误描述 |
| `retry_count` | SMALLINT | 实际重试次数 |
| `eval_latency_ms` | INTEGER | 评估总耗时（含重试），毫秒 |
| `evaluated_at` | TIMESTAMPTZ | 评估完成时间 |

> `eval_log` 不存储 `source_record_id`。调度层负责维护 `source_record_id → eval_id` 的映射。

### llm_call_log

仅 `llm_judge` 类型写入，关联 `eval_log`。每次重试写一条（`attempt_number` 递增）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | 自生成 |
| `eval_log_id` | UUID FK | 关联 eval_log.id |
| `judge_model` | VARCHAR(128) | 实际使用的模型 |
| `prompt_system` | TEXT | 完整 System Prompt |
| `prompt_user` | TEXT | 完整 User Prompt（动态注入后） |
| `raw_response` | JSONB | LLM API 原始返回 |
| `input_tokens` | INTEGER | 输入 token 数 |
| `output_tokens` | INTEGER | 输出 token 数 |
| `llm_latency_ms` | INTEGER | 纯 LLM 调用耗时（不含重试等待） |
| `attempt_number` | SMALLINT | 第几次尝试，首次为 1 |

---

## 重试机制

重试逻辑封装在各 Evaluator 内部，调度层只看到成功或最终失败，无需关心中间过程。

| 配置项 | 默认值 |
|--------|--------|
| 最大尝试次数 | 3（含首次） |
| 退避策略 | 指数退避，等待时间 = min(2^attempt, 10)s |
| 抖动 | ±0.5s 随机抖动 |

**触发重试的异常：**

| 异常 | 重试 |
|------|------|
| `RateLimitError (429)` | ✅ |
| `APITimeoutError` | ✅ |
| `ServiceUnavailableError (503)` | ✅ |
| `ParseError`（响应解析失败） | ❌ |
| `AuthenticationError (401/403)` | ❌ |
| `InvalidRequestError (400)` | ❌ |

---

## 错误码

| 错误码 | HTTP | 说明 | 调度层是否可重试 |
|--------|------|------|----------------|
| `VALIDATION_ERROR` | 422 | 通用字段校验失败 | ❌ |
| `UNKNOWN_METRIC_TYPE` | 422 | metric_type 未注册 | ❌ |
| `CONFIG_VALIDATION_ERROR` | 422 | metric 级别字段校验失败 | ❌ |
| `LLM_API_ERROR` | 500 | LLM API 错误（重试耗尽） | ✅ |
| `LLM_TIMEOUT` | 500 | LLM 超时（重试耗尽） | ✅ |
| `PARSE_ERROR` | 500 | LLM 返回无法解析 | ❌ 需排查 prompt |
| `INTERNAL_ERROR` | 500 | 未预期内部错误 | 视情况 |

---

## 项目结构

```
evaluation-service/
├── app/
│   ├── main.py                      # FastAPI 初始化
│   ├── api/v1/
│   │   └── evaluate.py              # 路由：POST /evaluate, GET /health
│   ├── evaluators/
│   │   ├── __init__.py              # import 各 evaluator，触发注册
│   │   ├── base.py                  # BaseEvaluator, EvalRecord, EvalConfig, EvalResult
│   │   ├── registry.py              # EvaluatorRegistry 单例
│   │   └── llm_judge_evaluator.py
│   ├── models/
│   │   ├── request.py               # EvaluateRequest（Pydantic）
│   │   └── response.py              # EvaluateResponse, ErrorResponse（Pydantic）
│   ├── db/
│   │   ├── connection.py            # 数据库连接池
│   │   ├── eval_log_repo.py
│   │   └── llm_call_log_repo.py
│   ├── tasks/
│   │   └── persist.py               # Background Task：写 eval_log + llm_call_log
│   └── exceptions.py                # EvaluationError, ParseError, ConfigValidationError ...
├── tests/
│   ├── unit/                        # 各 Evaluator 单元测试（mock LLM API）
│   └── integration/                 # 完整接口测试
├── migrations/                      # Alembic 迁移文件
├── .env.example
├── pyproject.toml
└── README.md
```

---

## 已注册 Evaluator

### llm_judge

| 属性 | 值 |
|------|----|
| `metric_type` | `llm_judge` |
| 文件 | `app/evaluators/llm_judge_evaluator.py` |
| `eval_config` 必填字段 | `judge_model`、`criteria` |
| 支持的 criteria | `accuracy` `completeness` `clarity` `relevance` `coherence`（可自定义） |
| 预期耗时 | 3–15s（首次），含重试最长约 45s |

---

*新增 Evaluator 后请在此章节追加对应说明。*
