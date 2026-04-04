# LLM Judge Evaluator

## 架构

```
API 层（路由/存储） → Registry 层（发现/校验） → Metrics 层（纯评估逻辑）
```

三层职责分离，Metrics 不依赖任何业务层代码，只依赖 `call_llm`。

## 文件结构

```
app/evaluators/
├── __init__.py                 # 注册所有 evaluator 类型到顶层 registry
├── registry.py                 # EvaluatorRegistry 顶层路由
├── llm_judge/                  # LLM Judge 类
│   ├── __init__.py             # 导入即注册所有 LLM-judge metric
│   ├── registry.py             # LLMJudgeRegistry 子 registry
│   ├── Faithfulness.py         # Metric 实现
│   ├── FactualCorrectness.py   # Metric 实现
│   └── README.md
├── performance/                # 公式类（未来扩展）
│   └── ...
```

## 如何注册一个新 Metric

### 1. 创建 Metric 类

在 `app/evaluators/llm_judge/` 下新建文件，实现一个朴素类，必须具备以下属性：

| 属性 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 全局唯一标识，用于 registry 查找和 API 路由 |
| `required_fields` | `list[str]` | evaluate 所需的必填字段，registry 用于入参校验 |
| `optional_fields` | `list[str]` | 选填字段（可省略，默认空列表） |
| `evaluate` | `async def` | 统一评估入口，接收关键字参数，返回 dict |

```python
class MyMetric:
    name: str = "my_metric"
    required_fields: list[str] = ["response", "reference"]
    optional_fields: list[str] = ["context"]  # 可省略

    async def evaluate(self, response: str, reference: str, context: str | None = None) -> dict:
        # ... 调用 call_llm 做评估 ...
        return {"score": 0.9, "reason": "..."}
```

约束：
- 不继承基类，不引用 registry
- 内部通过 `from app.utils.llm_utils import call_llm` 调用 LLM
- Prompt 模板写在 `resource/prompt/prompt.yaml`

### 2. 注册到子 Registry

在 `llm_judge/__init__.py` 中导入并注册：

```python
from app.evaluators.llm_judge.MyMetric import MyMetric
from app.evaluators.llm_judge.registry import llm_judge_registry

llm_judge_registry.register(MyMetric())
```

`register()` 会通过 duck typing 检查 `name`、`required_fields`、`evaluate` 是否存在，缺失则抛 `TypeError`。

### 3. 注册新的 Evaluator 类型（未来扩展）

```python
# app/evaluators/__init__.py
from app.evaluators.performance import performance_registry
evaluator_registry.register_type("performance", performance_registry)
```

顶层 `EvaluatorRegistry` 自动路由，无需改现有代码。

## Registry 运行机制

### 顶层 EvaluatorRegistry（`app/evaluators/registry.py`）

全局单例 `evaluator_registry`，按 evaluator 类型路由到子 registry：

| 方法 | 说明 |
|------|------|
| `register_type(type, sub_registry)` | 注册一个 evaluator 类型 |
| `get(type, name)` | 按类型 + 名称获取 metric 实例 |
| `validate_record(type, name, record)` | 校验 record 字段 |
| `list_types()` | 返回所有已注册的 evaluator 类型 |
| `list_metrics(type)` | 返回某类型下的所有 metric name |

典型调用流程（API 层）：

```python
evaluator_registry.validate_record("llm_judge", "faithfulness", record)
metric = evaluator_registry.get("llm_judge", "faithfulness")
result = await metric.evaluate(**record)
```

### LLM Judge 子 Registry（`app/evaluators/llm_judge/registry.py`）

| 方法 | 说明 |
|------|------|
| `register(metric)` | 注册 metric，duck typing 校验 |
| `get(name)` | 获取 metric，未注册抛 `KeyError` |
| `validate_record(name, record)` | 校验 required_fields，缺字段抛 `ValueError` |
| `list_metrics()` | 返回所有已注册 metric name |

## Prompt 模板

所有 Prompt 定义在 `resource/prompt/prompt.yaml`，通过 `app/utils/constants.py` 的 `PROMPT_DIR` 引用。修改 Prompt 只需编辑 yaml 文件，无需改代码。

## LLM 配置

LLM 调用统一通过 `call_llm()`（`app/utils/llm_utils.py`），内置重试和错误分类：

- **非重试错误**：缺环境变量（`ValueError`）、认证失败、请求格式错误 → 立即抛出
- **可重试错误**：超时、限流、503 → 指数退避重试

### 环境变量

LLM client 的所有配置通过环境变量管理，定义在 `app/utils/config.py` 的 `LLMSettings` 类中。

#### 必填项

启动前必须在 `.env` 文件或系统环境变量中设置：

| 环境变量 | 说明 |
|---------|------|
| `AZURE_OPENAI_API_KEY` | Azure OpenAI 的 API Key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI 的终结点地址 |

如果未设置，`call_llm()` 调用时会抛出 `ValueError`。

#### 可选项（有默认值）

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `AZURE_OPENAI_API_VERSION` | `2025-01-01-preview` | Azure OpenAI API 版本 |
| `LLM_MODEL` | `gpt-4.1` | 使用的模型名称 |
| `LLM_TEMPERATURE` | `0.0` | 生成温度 |
| `LLM_MAX_ATTEMPTS` | `3` | 最大重试次数 |
| `LLM_BASE_WAIT` | `2.0` | 指数退避基础等待时间（秒） |
| `LLM_MAX_WAIT` | `10.0` | 最大等待时间（秒） |
| `LLM_JITTER` | `0.5` | 随机抖动范围（秒） |

#### 配置生效流程

```
.env / 系统环境变量
       ↓  pydantic_settings 自动读取
LLMSettings (app/utils/config.py)
       ↓  llm_settings 单例
get_llm_client() / call_llm() (app/utils/llm_utils.py)
```

1. `LLMSettings` 继承 `BaseSettings`，启动时自动从 `.env` 文件和环境变量加载
2. 全局单例 `llm_settings` 在 `app/utils/config.py` 中创建
3. `get_llm_client()` 从 `llm_settings` 读取 key/endpoint 创建 `AsyncAzureOpenAI`
4. `call_llm()` 从 `llm_settings` 读取 model/temperature/重试参数执行调用

#### 修改配置

- **改默认值**：直接修改 `app/utils/config.py` 中 `LLMSettings` 的字段默认值
- **运行时覆盖**：在 `.env` 文件中设置对应的环境变量名即可覆盖默认值，无需改代码

#### 快速测试

```bash
# 在项目根目录执行
python -m app.utils.llm_utils
```

会打印当前所有配置，并用 `call_llm()` 发送一条测试请求验证连通性。
