# Local Setup Guide

## 1. Prerequisites

- Python >= 3.11
- Git

## 2. Clone & Install Dependencies

```bash
git clone <repo-url>
cd evaluation-service

# Create virtual environment (recommended)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` — at minimum fill in the following two (all others have defaults):

```env
# ===== Required =====
AZURE_OPENAI_API_KEY=your-azure-openai-key
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/

# ===== Has defaults, optional overrides =====
AZURE_OPENAI_API_VERSION=2025-01-01-preview
LLM_MODEL=gpt-4.1
LLM_TEMPERATURE=0.0
LLM_MAX_ATTEMPTS=3
DB_BACKEND=local
SQLITE_DB_PATH=data/evaluation.db
LOG_LEVEL=INFO
```

### Full Environment Variable Reference

#### Azure OpenAI (LLM Calls)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AZURE_OPENAI_API_KEY` | **Yes** | | Azure OpenAI API Key |
| `AZURE_OPENAI_ENDPOINT` | **Yes** | | Azure OpenAI Endpoint URL |
| `AZURE_OPENAI_API_VERSION` | No | `2025-01-01-preview` | API version |
| `LLM_MODEL` | No | `gpt-4.1` | Model deployment name |
| `LLM_TEMPERATURE` | No | `0.0` | Generation temperature |
| `LLM_MAX_ATTEMPTS` | No | `3` | Max retry attempts (including first) |

#### Database

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DB_BACKEND` | No | `local` | `local` = SQLite, `azure` = remote Azure DB |
| `SQLITE_DB_PATH` | No | `data/evaluation.db` | SQLite file path (local mode only) |
| `AZURE_DB_URL` | No | `mock://placeholder` | Azure DB connection string (real value needed for azure mode) |

#### Application

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LOG_LEVEL` | No | `INFO` | Log level (DEBUG / INFO / WARNING / ERROR) |
| `APP_VERSION` | No | `1.0.0` | Version number (returned by health endpoint) |

## 4. Initialize Database

Only needed when `DB_BACKEND=local`, for initial table creation:

```bash
python -m app.db
```

Success when you see `Local SQLite DB initialized at: data/evaluation.db`.

> Automatically creates the `data/` directory and `evaluation.db` file.

## 5. Start the Service

```bash
python main.py
```

After the service starts, visit:
- Swagger Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/v1/evaluation/health

## 6. Quick Verification

```bash
# Check service status
curl http://localhost:8000/api/v1/evaluation/health

# Test single-metric evaluation (requires valid Azure OpenAI config)
curl -X POST http://localhost:8000/api/v1/evaluation/llm_judge/faithfulness \
  -H "Content-Type: application/json" \
  -d '{
    "response": "Gradient descent is an optimization algorithm",
    "retrieved_contexts": "Gradient Descent is an optimization algorithm used to minimize loss functions"
  }'

# Test batch evaluation
curl -X POST http://localhost:8000/api/v1/evaluation/batch \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": ["faithfulness", "factual_correctness"],
    "test_case": {
      "response": "Domestic and imported hepatitis B vaccines have no difference in safety",
      "retrieved_contexts": "Domestic and imported hepatitis B vaccines are identical in safety and efficacy, both can be used with confidence",
      "reference": "Domestic and imported hepatitis B vaccines are identical in safety and efficacy"
    }
  }'
```

## Common Issues

### `FileNotFoundError: Local SQLite database not found`

Run table creation first: `python -m app.db`

### `ValueError: AZURE_OPENAI_API_KEY is required but not set`

Check that `.env` exists and `AZURE_OPENAI_API_KEY` is set. Make sure to run from the project root directory.

### `.env` changes not taking effect

`.env` is loaded once at service startup. Restart the service after making changes.
