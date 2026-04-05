# Metrics 架构重构 Task

## 重构目标

将 metrics 层从业务逻辑中解耦，实现三层职责分离：

```
API 层（路由/存储） → Registry 层（发现/校验） → Metrics 层（纯评估逻辑）
```

核心原则：
- Metrics 不依赖任何业务层代码，只依赖 `call_llm`
- 每个 metric 是独立的朴素类，不继承基类，不自己注册
- 注册在 registry 中集中完成，通过 duck typing 校验（检查 name、required_fields、evaluate）
- API 层负责请求解析、响应组装、数据存储

---

## 已完成

### 1. utils 包 (`app/utils/`)
- [x] `config.py` — `DBSettings` + `LLMSettings` + `AppSettings`（合并旧 app/config.py）
- [x] `logger.py` — `get_logger()` 通用 logger 工厂
- [x] `llm_utils.py` — `get_llm_client()` + `call_llm(messages, response_format)`
  - 使用 `AsyncAzureOpenAI`
  - 内置指数退避重试，不暴露 retry_count
  - `response_format` 支持 dict 或 pydantic model（自动用 parse()）
  - 非重试错误（ValueError/AuthenticationError/BadRequestError）直接抛出
- [x] `llm_tracker.py` — ContextVar 追踪 LLM 调用元数据
  - `start_tracking()` / `get_tracked_calls()` / `record_call()`
  - 自动记录 messages、raw_response、tokens、latency、attempt
  - metric 层无需改动，`call_llm()` 内部自动追踪
- [x] `constants.py` — `PROMPT_DIR` + `DEFAULT_DB_PATH`（基于项目根目录的绝对路径）

### 2. LLM Judge 包 (`app/evaluators/llm_judge/`)
- [x] `Faithfulness.py` — `name="faithfulness"`, `required_fields=["response", "retrieved_contexts"]`, `optional_fields=["user_input"]`, `async evaluate()`
- [x] `FactualCorrectness.py` — `name="factual_correctness"`, `required_fields=["reference", "response"]`, `async evaluate()`
- [x] `registry.py` — `llm_judge_registry = MetricRegistry()` 子 registry 单例
- [x] `__init__.py` — 导入即自动注册两个 metric
- [x] `README.md` — LLM Judge 系统文档

### 3. Performance 包 (`app/evaluators/performance/`)
- [x] `registry.py` — `performance_registry = MetricRegistry()` 空壳，待添加公式类 metric
- [x] `__init__.py` — 预留注册入口

### 4. 共享 Registry (`app/evaluators/registry.py`)
- [x] `MetricRegistry` — 通用子 registry，duck typing 校验 + record 字段校验 + list_metrics
- [x] `EvaluatorRegistry` — 顶层路由，按 evaluator_type（llm_judge/performance）分发到子 registry
- [x] `evaluator_registry` 全局单例
- [x] `app/evaluators/__init__.py` — 注册所有 evaluator type 到顶层 registry

### 5. API 层 (`app/api/v1/evaluate.py`)
- [x] 动态路由注册，每个 metric 一条独立路由
- [x] 每个 metric 定义自己的 `request_model`（Pydantic）
- [x] `eval_id` optional（default_factory=uuid4，examples 动态生成）
- [x] 响应格式：`{eval_id, status, result: {score, reason, ...}, metadata: {...}}`
- [x] 错误映射：openai 异常 → HTTP status
- [x] LLM 调用追踪：evaluate 前后 start/get tracking，传给 persist task

### 6. DB 重构
- [x] Config 合并：`app/config.py` 删除，统一到 `app/utils/config.py`（DBSettings/LLMSettings/AppSettings）
- [x] DB 路径常量化：`DEFAULT_DB_PATH` 在 `constants.py`，不再依赖运行时目录
- [x] 表重命名：`eval_log` → `evaluation_result`，`llm_call_log` → `llm_metadata`
- [x] Model 重命名：`EvalLog` → `EvaluationResult`，`LLMCallLog` → `LLMMetadata`
- [x] 字段清理：删除 `reasoning`、`retry_count`；`scores_detail` → `reason`
- [x] Latency 统一：`llm_latency_ms` → `llm_latency_s`（Float）
- [x] `llm_metadata.messages` — JSON 列存原始 `[{role, content}, ...]`
- [x] `llm_metadata.raw_response` — 存 `{content, model, finish_reason}`（避免 Pydantic 序列化 warning）
- [x] 持久化事务：`persist_eval_result` 写 evaluation_result + 所有 llm_metadata，一次 commit
- [x] Migration 0001/0002 已同步

### 7. 当前表结构
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
- `0da923f` — utils 包 + metrics 层重写
- `b35a061` — MetricRegistry + duck typing 校验
- `3ae6833` — 重组为 type-based 包
- `120aaa7` — API 层重构（per-metric 路由）
- `13f2701` — 旧文件清理
- `68cb0b3` — 响应格式重构 + eval_id optional + README
- `1a48f34` — latency 从 ms 改为秒
- `c892aa4` — Config 统一 + DB 表名/字段重构
- `7fb4eab` — LLM tracking (ContextVar) + persist llm_metadata + DB 路径常量化

---

## 待完成

### 9. Batch API（调度层统一入口）
- [x] 新增 `POST /api/v1/evaluation/batch`
- [x] 请求模型：
  ```json
  {
    "task_id": "uuid（可选）",
    "metrics": ["faithfulness", "factual_correctness"],
    "test_case": { "response": "...", "retrieved_contexts": "...", "reference": "...", ... }
  }
  ```
- [x] 内部逻辑：遍历 metrics → 从 test_case 提取字段 → 用 required_fields 校验 → 调用 evaluate
- [x] 并发执行：`asyncio.gather` 并发跑多个 metric（非串行）
- [x] DB 变动：`evaluation_result` 新增 `task_id` 列（可选，同 task 下多 metric 共享）
- [x] 保留现有 per-metric 路由（单用户 / Swagger）
- [x] 两套路由共享 `_evaluate_single()` 核心逻辑
- [x] `EvaluatorRegistry.find_metric(name)` — 按名称跨类型查找 metric
- [x] Migration 0003 — 新增 task_id 列 + index

### 10. 旧文件清理
- [ ] `app/evaluators/base.py` — 待删
- [ ] `tests/unit/` — 旧测试需重写

### 11. 测试
- [ ] 每个 metric 独立单元测试
- [ ] registry 注册和校验测试
- [ ] batch endpoint 集成测试
