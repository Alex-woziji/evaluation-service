"""
Integration tests for POST /api/v1/evaluation/evaluate and GET /health.
LLM API calls are fully mocked — no network or database required.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.tasks.persist import persist_eval_result

# Suppress background DB writes in all tests
pytestmark = pytest.mark.asyncio


@pytest.fixture
def eval_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def base_payload(eval_id: str) -> dict:
    return {
        "eval_id": eval_id,
        "metric_type": "llm_judge",
        "record": {
            "input": "请解释梯度下降",
            "output": "梯度下降是一种优化算法",
            "reference": "梯度下降（Gradient Descent）是…",
        },
        "eval_config": {
            "judge_model": "gpt-4o",
            "criteria": ["accuracy", "completeness", "clarity"],
            "rubric": "评估回答质量",
        },
    }


def _mock_llm(criteria_scores: dict, reasoning: str = "good answer"):
    content = json.dumps({"criteria_scores": criteria_scores, "reasoning": reasoning})
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 40
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model_dump.return_value = {"mocked": True}
    return response


@pytest.fixture
def async_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Health ─────────────────────────────────────────────────────────────────────

async def test_health(async_client):
    async with async_client as client:
        resp = await client.get("/api/v1/evaluation/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "llm_judge" in body["registered_evaluators"]


# ── Success path ───────────────────────────────────────────────────────────────

async def test_evaluate_success(async_client, base_payload, eval_id):
    mock_resp = _mock_llm({"accuracy": 0.9, "completeness": 0.85, "clarity": 0.8})
    with (
        patch("app.evaluators.llm_judge_evaluator.AsyncOpenAI") as mock_cls,
        patch("app.api.v1.evaluate.persist_eval_result", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        mock_cls.return_value = mock_client

        async with async_client as client:
            resp = await client.post("/api/v1/evaluation/evaluate", json=base_payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["eval_id"] == eval_id
    assert body["metric_type"] == "llm_judge"
    assert body["status"] == "success"
    assert 0.0 <= body["score"] <= 1.0
    assert set(body["scores_detail"].keys()) == {"accuracy", "completeness", "clarity"}
    assert body["retry_count"] == 0
    assert body["eval_latency_ms"] >= 0


# ── Validation errors ──────────────────────────────────────────────────────────

async def test_missing_eval_id_returns_422(async_client, base_payload):
    del base_payload["eval_id"]
    async with async_client as client:
        resp = await client.post("/api/v1/evaluation/evaluate", json=base_payload)
    assert resp.status_code == 422


async def test_missing_record_input_returns_422(async_client, base_payload):
    base_payload["record"]["input"] = ""
    async with async_client as client:
        resp = await client.post("/api/v1/evaluation/evaluate", json=base_payload)
    assert resp.status_code == 422


async def test_unknown_metric_type_returns_422(async_client, base_payload):
    base_payload["metric_type"] = "does_not_exist"
    async with async_client as client:
        resp = await client.post("/api/v1/evaluation/evaluate", json=base_payload)
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["error"] == "UNKNOWN_METRIC_TYPE"


async def test_missing_judge_model_returns_422(async_client, base_payload):
    del base_payload["eval_config"]["judge_model"]
    async with async_client as client:
        resp = await client.post("/api/v1/evaluation/evaluate", json=base_payload)
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["error"] == "CONFIG_VALIDATION_ERROR"


async def test_empty_criteria_returns_422(async_client, base_payload):
    base_payload["eval_config"]["criteria"] = []
    async with async_client as client:
        resp = await client.post("/api/v1/evaluation/evaluate", json=base_payload)
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["error"] == "CONFIG_VALIDATION_ERROR"


async def test_invalid_score_range_returns_422(async_client, base_payload):
    base_payload["eval_config"]["score_range"] = {"min": 1.0, "max": 0.0}
    async with async_client as client:
        resp = await client.post("/api/v1/evaluation/evaluate", json=base_payload)
    assert resp.status_code == 422


# ── LLM error paths ────────────────────────────────────────────────────────────

async def test_parse_error_returns_500(async_client, base_payload):
    bad_message = MagicMock()
    bad_message.content = "this is not json"
    bad_choice = MagicMock()
    bad_choice.message = bad_message
    bad_usage = MagicMock()
    bad_usage.prompt_tokens = 10
    bad_usage.completion_tokens = 5
    bad_response = MagicMock()
    bad_response.choices = [bad_choice]
    bad_response.usage = bad_usage
    bad_response.model_dump.return_value = {}

    with (
        patch("app.evaluators.llm_judge_evaluator.AsyncOpenAI") as mock_cls,
        patch("app.api.v1.evaluate.persist_eval_result", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=bad_response)
        mock_cls.return_value = mock_client

        async with async_client as client:
            resp = await client.post("/api/v1/evaluation/evaluate", json=base_payload)

    assert resp.status_code == 500
    assert resp.json()["detail"]["error"] == "PARSE_ERROR"


async def test_rate_limit_exhausted_returns_500(async_client, base_payload):
    import openai

    with (
        patch("app.evaluators.llm_judge_evaluator.AsyncOpenAI") as mock_cls,
        patch("app.api.v1.evaluate.persist_eval_result", new_callable=AsyncMock),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError("rate limit", response=MagicMock(), body={})
        )
        mock_cls.return_value = mock_client

        async with async_client as client:
            resp = await client.post("/api/v1/evaluation/evaluate", json=base_payload)

    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"]["error"] == "LLM_API_ERROR"
    assert body["detail"]["retry_count"] == 2
