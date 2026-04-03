# Evaluation Service

LLM 评估平台的指标计算层。职责单一：接收单条 record，执行指标计算，同步返回结果，后台异步写执行日志。

> **不感知** ETL、不感知调度、不感知中间表 ID 体系。

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 填写 DB_BACKEND、SQLITE_DB_PATH、OPENAI_API_KEY 等

# 初始化本地 SQLite（仅 DB_BACKEND=local 时需要）
python -m app.db

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 运行测试（无需数据库 / 网络）
pytest
```

---

## 项目结构

```
evaluation-service/
├── app/
│   ├── main.py                      # FastAPI 初始化 + 全局异常处理
│   ├── config.py                    # pydantic-settings 环境变量
│   ├── exceptions.py                # EvaluationError 体系
│   ├── api/v1/
│   │   └── evaluate.py              # POST /evaluate · GET /health
│   ├── evaluators/
│   │   ├── __init__.py              # import 各 evaluator，触发注册
│   │   ├── base.py                  # EvalRecord / EvalConfig / EvalResult / BaseEvaluator
│   │   ├── registry.py              # EvaluatorRegistry 单例
│   │   └── llm_judge_evaluator.py   # LLMJudgeEvaluator（含重试）
│   ├── models/
│   │   ├── request.py               # EvaluateRequest（Pydantic v2）
│   │   └── response.py              # EvaluateResponse / ErrorResponse
│   ├── db/
│   │   ├── models.py                # SQLAlchemy ORM：EvalLog · LLMCallLog
│   │   ├── connection.py            # 本地 SQLite / Azure DB 连接选择
│   │   ├── init_db.py               # 本地 SQLite 初始化脚本
│   │   ├── __main__.py              # 支持 python -m app.db
│   │   ├── README.md                # DB 配置与使用说明
│   │   ├── eval_log_repo.py         # upsert_eval_log
│   │   └── llm_call_log_repo.py     # insert_llm_call_log
│   └── tasks/
│       └── persist.py               # BackgroundTask：写 eval_log + llm_call_log
├── migrations/
│   ├── env.py                       # Alembic async env
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py   # 建表：eval_log · llm_call_log
├── tests/
│   ├── unit/
│   │   ├── test_llm_judge.py        # LLMJudgeEvaluator 单元测试（mock LLM）
│   │   └── test_registry.py        # EvaluatorRegistry 单元测试
│   └── integration/
│       └── test_evaluate_api.py     # 完整接口集成测试（mock LLM）
├── pyproject.toml
├── alembic.ini
└── .env.example
```

---

## API

### POST /api/v1/evaluation/evaluate

同步执行单条 record 的评估。

**Request**

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

**Response 200**

```json
{
  "eval_id": "550e8400-e29b-41d4-a716-446655440000",
  "metric_type": "llm_judge",
  "status": "success",
  "score": 0.87,
  "scores_detail": {"accuracy": 0.90, "completeness": 0.85, "clarity": 0.85},
  "reasoning": "...",
  "retry_count": 0,
  "eval_latency_ms": 4312,
  "evaluated_at": "2025-04-03T10:23:45.123Z"
}
```

| HTTP | error 字段 | 含义 | 可重试 |
|------|-----------|------|-------|
| 422 | `VALIDATION_ERROR` | Pydantic 校验失败 | ❌ |
| 422 | `UNKNOWN_METRIC_TYPE` | metric_type 未注册 | ❌ |
| 422 | `CONFIG_VALIDATION_ERROR` | metric 级别配置缺失 | ❌ |
| 500 | `LLM_API_ERROR` | LLM API 错误（重试耗尽） | ✅ |
| 500 | `LLM_TIMEOUT` | LLM 超时（重试耗尽） | ✅ |
| 500 | `PARSE_ERROR` | LLM 返回无法解析 | ❌ |

### GET /api/v1/evaluation/health

```json
{"status": "ok", "registered_evaluators": ["llm_judge"], "version": "1.0.0"}
```

---

## 新增 Evaluator

1. 在 `app/evaluators/` 创建新文件，继承 `BaseEvaluator`，设置 `metric_type`，用 `@registry.register` 装饰
2. 在 `app/evaluators/__init__.py` 添加 import 触发注册
3. 在本 README 追加说明

---

## 已注册 Evaluator

### llm_judge

| 属性 | 值 |
|------|----|
| `metric_type` | `llm_judge` |
| 必填 eval_config | `judge_model`、`criteria` |
| 支持 criteria | `accuracy` `completeness` `clarity` `relevance` `coherence`（可自定义） |
| 重试策略 | 指数退避 3 次，等待 = min(2^n, 10)s ±0.5s |
| 预期耗时 | 3–15 s（首次），含重试最长约 45 s |

---

## 重试机制

| 异常 | 重试 |
|------|------|
| `RateLimitError (429)` | ✅ |
| `APITimeoutError` | ✅ |
| `ServiceUnavailableError (503)` | ✅ |
| `ParseError` | ❌ |
| `AuthenticationError` | ❌ |
| `BadRequestError (400)` | ❌ |
