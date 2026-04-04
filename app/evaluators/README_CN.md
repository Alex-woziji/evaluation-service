# Evaluators

本目录包含 evaluation-service 的评估器框架。

## 架构

```
criteria.py              CriteriaType 枚举 — 所有受支持的评估维度
registry.py              EvaluatorRegistry — 评估器 + 维度查询
base.py                  BaseEvaluator、EvalRecord、EvalConfig、EvalResult
llm_judge_evaluator.py   基于 LLM 的评判评估器（metric_type="llm_judge"）
__init__.py              导入评估器以触发 @registry.register 注册
```

## 两层注册机制

### 1. 指标类型（`metric_type`）

每个评估器类设置唯一的 `metric_type` 字符串，通过 `@registry.register` 装饰器注册：

```python
from app.evaluators.base import BaseEvaluator
from app.evaluators.registry import registry

@registry.register
class MyEvaluator(BaseEvaluator):
    metric_type = "my_metric"

    async def evaluate(self, record, config):
        ...
```

API 路由通过 `request.metric_type` → `registry.get(metric_type)` 查找评估器。未注册的类型返回 `422 UNKNOWN_METRIC_TYPE`。

### 2. 评估维度（`CriteriaType` 枚举）

Criteria 是评估器打分的细粒度维度（如 `accuracy`、`clarity`）。它们以枚举形式集中注册在 `criteria.py` 中：

```python
class CriteriaType(str, Enum):
    accuracy = "accuracy"
    completeness = "completeness"
    clarity = "clarity"
```

API 会拒绝不在该枚举中的 criterion，返回 `422 CRITERIA_VALIDATION_ERROR`。

**新增维度**：在 `criteria.py` 的 `CriteriaType` 中加一行即可。

## 校验钩子

`BaseEvaluator` 提供两个可覆盖的钩子，在评估执行前运行：

### `validate_record(record: dict, config: EvalConfig)`

校验传入的 `record` 字典是否包含当前指标/维度组合所需的字段。失败时抛出 `RecordValidationError(field="record.xxx", message="...")`。

示例 — `accuracy` 要求必须提供 `reference`：

```python
def validate_record(self, record, config):
    if "accuracy" in config.criteria:
        ref = record.get("reference")
        if not isinstance(ref, str) or not ref.strip():
            raise RecordValidationError(
                "reference is required when criteria includes accuracy",
                field="record.reference",
            )
```

### `validate_config(config: EvalConfig)`

校验评估器特有的配置字段。失败时抛出 `ConfigValidationError(field="eval_config.xxx", message="...")`。

示例 — `llm_judge` 要求 `judge_model` 非空且 `criteria` 列表不为空：

```python
def validate_config(self, config):
    if not config.judge_model:
        raise ConfigValidationError(
            "judge_model is required for llm_judge",
            field="eval_config.judge_model",
        )
```

## API 中的校验执行顺序

1. Pydantic 解析 `EvaluateRequest`（结构校验）。
2. `registry.get(metric_type)` — 未注册返回 `422 UNKNOWN_METRIC_TYPE`。
3. 维度枚举校验 — 任何不支持的 criterion 返回 `422 CRITERIA_VALIDATION_ERROR`。
4. `evaluator.validate_record(record, config)` — `422 RECORD_VALIDATION_ERROR`。
5. `evaluator.validate_config(config)` — `422 CONFIG_VALIDATION_ERROR`。
6. `evaluator.evaluate(record, config)` — 执行评估。

## 如何新增一个评估器

1. 创建新文件，如 `app/evaluators/performance_evaluator.py`。
2. 定义评估器类：

```python
from app.evaluators.base import BaseEvaluator, EvalConfig, EvalRecord, EvalResult
from app.evaluators.registry import registry

@registry.register
class PerformanceEvaluator(BaseEvaluator):
    metric_type = "performance"

    def validate_record(self, record, config):
        # 校验该指标所需的 record 字段
        ...

    def validate_config(self, config):
        # 校验该指标所需的 config 字段
        ...

    async def evaluate(self, record: EvalRecord, config: EvalConfig) -> EvalResult:
        ...
```

3. 在 `app/evaluators/__init__.py` 中导入，触发注册：

```python
from app.evaluators import performance_evaluator  # noqa: F401
```

4. 如果评估器引入了新的评估维度，在 `criteria.py` 的 `CriteriaType` 中添加。
5. 如果某个维度要求特定的 record 字段，在对应评估器的 `validate_record` 中添加校验。

## 如何新增一个评估维度

1. 在 `criteria.py` 的 `CriteriaType` 中添加枚举值。
2. 如果该维度要求特定的 record 字段，在对应评估器的 `validate_record` 中添加校验逻辑。
3. 补充测试覆盖：
   - 合法维度被接受。
   - 缺少必要的 record 字段时返回 `422 RECORD_VALIDATION_ERROR`。
   - 未注册的维度返回 `422 CRITERIA_VALIDATION_ERROR`。

## 数据流：请求 record → EvalRecord

API 以通用 `Dict[str, Any]` 接收 `record`。路由在校验通过后将其映射为内部 `EvalRecord` 数据类：

```python
record = EvalRecord(
    input=request.record["input"],
    output=request.record["output"],
    reference=request.record.get("reference"),
    metadata={
        k: v for k, v in request.record.items()
        if k not in {"input", "output", "reference"}
    },
)
```

请求 record 中的额外字段会保留在 `EvalRecord.metadata` 中。

## 错误码

| 错误码 | HTTP 状态码 | 触发条件 |
|---|---|---|
| `UNKNOWN_METRIC_TYPE` | 422 | `metric_type` 未在 registry 中注册 |
| `CRITERIA_VALIDATION_ERROR` | 422 | criterion 不在 `CriteriaType` 枚举中 |
| `RECORD_VALIDATION_ERROR` | 422 | record 缺少维度要求的字段 |
| `CONFIG_VALIDATION_ERROR` | 422 | 评估器特有配置校验失败 |
