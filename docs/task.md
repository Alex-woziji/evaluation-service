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
- [x] `config.py` — `LLMSettings`，从环境变量读取 Azure OpenAI 配置和重试参数
- [x] `logger.py` — `get_logger()` 通用 logger 工厂
- [x] `llm_utils.py` — `get_llm_client()` + `call_llm(messages, response_format)`
  - 使用 `AsyncAzureOpenAI`
  - 内置指数退避重试，不暴露 retry_count
  - `response_format` 支持 dict 或 pydantic model（自动用 parse()）
  - 非重试错误（ValueError/AuthenticationError/BadRequestError）直接抛出
  - 环境变量：`AZURE_OPENAI_API_KEY`、`AZURE_OPENAI_ENDPOINT`、`AZURE_OPENAI_API_VERSION`
  - 可选配置：`LLM_MODEL`、`LLM_TEMPERATURE`、`LLM_MAX_ATTEMPTS`、`LLM_BASE_WAIT`、`LLM_MAX_WAIT`、`LLM_JITTER`
- [x] `constants.py` — `PROMPT_DIR` 指向 `resource/prompt/prompt.yaml`

### 2. LLM Judge 包 (`app/evaluators/llm_judge/`)
- [x] `Faithfulness.py` — `name="faithfulness"`, `required_fields=["response", "retrieved_contexts"]`, `optional_fields=["user_input"]`, `async evaluate()`
- [x] `FactualCorrectness.py` — `name="factual_correctness"`, `required_fields=["reference", "response"]`, `async evaluate()`
- [x] `registry.py` — `llm_judge_registry = MetricRegistry()` 子 registry 单例
- [x] `__init__.py` — 导入即自动注册两个 metric
- [x] `README.md` — LLM Judge 系统文档（注册方式、运行机制、LLM 配置）

### 3. Performance 包 (`app/evaluators/performance/`)
- [x] `registry.py` — `performance_registry = MetricRegistry()` 空壳，待添加公式类 metric
- [x] `__init__.py` — 预留注册入口

### 4. 共享 Registry (`app/evaluators/registry.py`)
- [x] `MetricRegistry` — 通用子 registry，duck typing 校验 + record 字段校验 + list_metrics
- [x] `EvaluatorRegistry` — 顶层路由，按 evaluator_type（llm_judge/performance）分发到子 registry
- [x] `evaluator_registry` 全局单例
- [x] `app/evaluators/__init__.py` — 注册所有 evaluator type 到顶层 registry

### 5. 设计文档
- [x] `app/evaluators/llm_judge/README.md` — 架构说明 + 注册指南 + LLM 配置

### 6. Git 提交
- [x] `0da923f` — utils 包 + metrics 层重写（async call_llm）
- [x] `b35a061` — MetricRegistry + duck typing 校验 + record 校验
- [x] `3ae6833` — 重组为 llm_judge/performance 包 + 共享 MetricRegistry

---

## 待完成

### 7. API 层重构 (`app/api/v1/evaluate.py`)
- [x] 请求模型改为 `evaluator_type` + `metric_name` + `record` + `options`（一个请求 = 一个 metric）
- [x] 从 `evaluator_registry` 获取 metric，`validate_record` 校验，调用 `evaluate(**record)`
- [x] API 层计时 → `eval_latency_ms`
- [x] 简单 openai 异常 → HTTP status 映射（Auth→500, RateLimit→503, Timeout→504, BadRequest→500）
- [x] 响应模型简化：`score` + `detail`（除 score 外的全部 metric 输出）+ `reasoning`
- [x] 数据存储 `eval_log` 由 API 层 background task 负责
- [x] DB model 添加 `metric_name` 列，`metric_type` 复用为 `evaluator_type`
- [x] `.env` extra 字段兼容（`LLMSettings` 和 `Settings` 都加了 `extra="ignore"`）

### 8. 旧文件清理
- [ ] `app/evaluators/base.py` — API 重构完后删除（当前仍被旧测试引用）
- [ ] `app/evaluators/llm_judge_evaluator.py` — 同上
- [ ] `tests/unit/test_registry.py` — 旧 registry 测试，需重写
- [ ] `tests/unit/test_llm_judge.py` — 旧 evaluator 测试，需重写
- [ ] `tests/unit/test_metrics.py` — 引用已删除的旧 metrics 包，需重写

### 9. 测试
- [x] API 集成测试（9/9 passed：成功路径、校验错误、LLM 错误）
- [ ] 每个 metric 独立单元测试
- [ ] registry 注册和校验测试
