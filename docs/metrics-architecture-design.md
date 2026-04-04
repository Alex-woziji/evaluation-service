# Metrics 架构重构设计

## 核心原则：三层职责分离

```
┌─────────────────────────────────────┐
│  API 层                             │
│  路由 / 请求校验 / 响应组装 / 存储   │
├─────────────────────────────────────┤
│  注册层                             │
│  发现 metrics / 校验入参 / 路由分发   │
├─────────────────────────────────────┤
│  Metrics 层 (独立 pkg)              │
│  纯评估逻辑 / 只依赖 LLM client     │
│  定义自己需要什么字段 + 返回通用结果   │
└─────────────────────────────────────┘
```

依赖方向：API 层 → 注册层 → Metrics 层，单向依赖，不可反向。

---

## Metrics 层

### 职责

- 纯评估逻辑，不依赖任何业务层代码
- 每个_metric_定义自己需要的入参字段（`required_fields`）
- 返回业务无关的通用结果（`MetricResult`）
- 不引用_registry_，不关心自己被谁管理、怎么注册

### LLM Client 注入方式

metric 内部不持有_client_实例，通过工厂函数在每次 `evaluate` 调用时创建：

```python
from typing import Any, Callable, Dict
from openai import AsyncOpenAI

class BaseMetric:
    name: str = ""
    required_fields: list[str] = []
    description: str = ""

    def validate_record(self, record: Dict[str, Any]) -> None:
        for field_name in self.required_fields:
            value = record.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"'{field_name}' is required for metric '{self.name}'")

    async def evaluate(
        self,
        record: Dict[str, Any],
        config: Any,
        *,
        new_client: Callable[[], AsyncOpenAI],
    ) -> "MetricResult":
        ...
```

- `new_client` 是工厂函数，每次调用返回新的 `AsyncOpenAI` 实例
- token 由调用方（API 层）负责动态获取
- metric 在 `evaluate` 内部调用 `new_client()` 创建客户端，保证 token 最新

### 为什么不传入_client_实例

- token 是动态获取的，每次调用需要新 client
- 传入工厂函数比传入实例更灵活，token 获取时机最晚（实际调用前一刻）
- 一次 `evaluate` 内如果需要多次调 LLM，使用同一个 client 实例，token 一致

---

## 注册层

### 职责

- 集中注册所有 metrics，metric 不自己注册
- 注册后执行入参校验：根据 metric 声明的 `required_fields` 检查请求中的 record
- 缺少必要字段时抛出校验错误
- 提供 metric 的发现和查询能力

### 注册方式

metric 文件只定义类，不引用_registry_。注册在一个集中的地方完成：

```python
# registry 或 wiring 模块中集中注册
from app.evaluators.metrics.accuracy import AccuracyMetric
from app.evaluators.metrics.answer_relevance import AnswerRelevanceMetric
...

metric_registry.register(AccuracyMetric)
metric_registry.register(AnswerRelevanceMetric)
```

这样 metric 定义和注册解耦，metric 可以独立测试和复用。

---

## API 层

### 职责

- HTTP 路由定义
- 请求参数解析和基础校验（Pydantic）
- 组装 `new_client` 工厂函数（封装 token 获取逻辑）
- 调用注册层获取 metric、执行评估
- 将 MetricResult 转换为业务响应格式
- 负责数据的输入输出存储（eval_log、llm_call_log）

### 调用流程

```
HTTP Request
  → Pydantic 校验
  → 从 registry 获取 metric
  → 校验 record 必填字段
  → 构造 new_client 工厂
  → metric.evaluate(record, config, new_client=...)
  → 组装响应
  → 后台持久化
  → HTTP Response
```

---

## 不做的事

- 不引入 Protocol/接口抽象——只用一种 LLM client，`Callable[[], AsyncOpenAI]` 足够
- 不在 metric 内部处理重试和错误映射——这些是调用方的职责
- 不让 metric 感知 HTTP 状态码、数据库存储等业务概念
