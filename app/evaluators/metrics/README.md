# LLM Client 配置说明

## 环境变量

LLM client 的所有配置通过环境变量管理，定义在 `app/utils/config.py` 的 `LLMSettings` 类中。

### 必填项

启动前必须在 `.env` 文件或系统环境变量中设置：

| 环境变量 | 说明 |
|---------|------|
| `AZURE_OPENAI_API_KEY` | Azure OpenAI 的 API Key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI 的终结点地址 |

如果未设置，`call_llm()` 调用时会抛出 `ValueError`。

### 可选项（有默认值）

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `AZURE_OPENAI_API_VERSION` | `2025-01-01-preview` | Azure OpenAI API 版本 |
| `LLM_MODEL` | `gpt-4.1` | 使用的模型名称 |
| `LLM_TEMPERATURE` | `0.0` | 生成温度 |
| `LLM_MAX_ATTEMPTS` | `3` | 最大重试次数 |
| `LLM_BASE_WAIT` | `2.0` | 指数退避基础等待时间（秒） |
| `LLM_MAX_WAIT` | `10.0` | 最大等待时间（秒） |
| `LLM_JITTER` | `0.5` | 随机抖动范围（秒） |

## 配置生效流程

```
.env / 系统环境变量
       ↓  pydantic_settings 自动读取
LLMSettings (app/utils/config.py)
       ↓  llm_settings 单例
get_llm_client() / call_llm() (app/evaluators/metrics/llm_utils.py)
```

1. `LLMSettings` 继承 `BaseSettings`，启动时自动从 `.env` 文件和环境变量加载
2. 全局单例 `llm_settings` 在 `app/utils/config.py` 中创建
3. `get_llm_client()` 从 `llm_settings` 读取 key/endpoint 创建 `AsyncAzureOpenAI`
4. `call_llm()` 从 `llm_settings` 读取 model/temperature/重试参数执行调用

## 修改配置

- **改默认值**：直接修改 `app/utils/config.py` 中 `LLMSettings` 的字段默认值
- **运行时覆盖**：在 `.env` 文件中设置对应的环境变量名即可覆盖默认值，无需改代码

## 快速测试

```bash
# 在项目根目录执行
python -m app.evaluators.metrics.llm_utils
```

会打印当前所有配置，并用 `call_llm()` 发送一条测试请求验证连通性。
