# 本地启动指南

## 1. 环境要求

- Python >= 3.11
- Git

## 2. 克隆项目 & 安装依赖

```bash
git clone <repo-url>
cd evaluation-service

# 创建虚拟环境（推荐）
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填写以下两项（其他都有默认值，按需修改）：

```env
# ===== 必填 =====
AZURE_OPENAI_API_KEY=你的Azure OpenAI Key
AZURE_OPENAI_ENDPOINT=https://你的资源名.openai.azure.com/

# ===== 有默认值，可选覆盖 =====
AZURE_OPENAI_API_VERSION=2025-01-01-preview
LLM_MODEL=gpt-4.1
LLM_TEMPERATURE=0.0
LLM_MAX_ATTEMPTS=3
DB_BACKEND=local
SQLITE_DB_PATH=data/evaluation.db
LOG_LEVEL=INFO
```

### 环境变量完整参考

#### Azure OpenAI（LLM 调用）

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `AZURE_OPENAI_API_KEY` | **是** | | Azure OpenAI API Key |
| `AZURE_OPENAI_ENDPOINT` | **是** | | Azure OpenAI 终端地址 |
| `AZURE_OPENAI_API_VERSION` | 否 | `2025-01-01-preview` | API 版本 |
| `LLM_MODEL` | 否 | `gpt-4.1` | 模型部署名称 |
| `LLM_TEMPERATURE` | 否 | `0.0` | 生成温度 |
| `LLM_MAX_ATTEMPTS` | 否 | `3` | 最大重试次数（含首次） |

#### 数据库

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DB_BACKEND` | 否 | `local` | `local` = SQLite，`azure` = 远程 Azure DB |
| `SQLITE_DB_PATH` | 否 | `data/evaluation.db` | SQLite 文件路径（仅 local 模式） |
| `AZURE_DB_URL` | 否 | `mock://placeholder` | Azure DB 连接串（仅 azure 模式需要填真实值） |

#### 应用

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `LOG_LEVEL` | 否 | `INFO` | 日志级别（DEBUG / INFO / WARNING / ERROR） |
| `APP_VERSION` | 否 | `1.0.0` | 版本号（health 接口返回） |

## 4. 初始化数据库

仅 `DB_BACKEND=local` 时需要，首次建表：

```bash
python -m app.db
```

看到 `Local SQLite DB initialized at: data/evaluation.db` 即成功。

> 会自动创建 `data/` 目录和 `evaluation.db` 文件。

## 5. 启动服务

```bash
python main.py
```

服务启动后访问：
- Swagger 文档：http://localhost:8000/docs
- Health Check：http://localhost:8000/api/v1/evaluation/health

## 6. 快速验证

```bash
# 检查服务状态
curl http://localhost:8000/api/v1/evaluation/health

# 测试单指标评估（需要有效的 Azure OpenAI 配置）
curl -X POST http://localhost:8000/api/v1/evaluation/llm_judge/faithfulness \
  -H "Content-Type: application/json" \
  -d '{
    "response": "梯度下降是一种优化算法",
    "retrieved_contexts": "梯度下降（Gradient Descent）是一种用于最小化损失函数的优化算法"
  }'

# 测试批量评估
curl -X POST http://localhost:8000/api/v1/evaluation/batch \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": ["faithfulness", "factual_correctness"],
    "test_case": {
      "response": "国产乙肝疫苗与进口疫苗在安全性方面没有区别",
      "retrieved_contexts": "国产乙肝疫苗与进口乙肝疫苗在安全性和预防效果上完全相同，均可放心使用",
      "reference": "国产乙肝疫苗与进口乙肝疫苗在安全性和预防效果上完全相同"
    }
  }'
```

## 常见问题

### `FileNotFoundError: Local SQLite database not found`

首次运行需要先建表：`python -m app.db`

### `ValueError: AZURE_OPENAI_API_KEY is required but not set`

检查 `.env` 文件是否存在且 `AZURE_OPENAI_API_KEY` 已填写。确保从项目根目录启动。

### `.env` 修改后不生效

`.env` 在服务启动时一次性加载。修改后重启服务即可。
