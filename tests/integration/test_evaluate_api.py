"""Integration tests for per-metric evaluation endpoints and GET /health.

LLM API calls are fully mocked — no network or database required.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app

# Suppress background DB writes in all tests
pytestmark = pytest.mark.asyncio


@pytest.fixture
def eval_id() -> str:
    return str(uuid.uuid4())


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
    assert "llm_judge" in body["evaluators"]
    assert "faithfulness" in body["evaluators"]["llm_judge"]
    assert "factual_correctness" in body["evaluators"]["llm_judge"]


# ── Faithfulness ───────────────────────────────────────────────────────────────

async def test_evaluate_faithfulness_success(async_client, eval_id):
    payload = {
        "eval_id": eval_id,
        "response": "Gradient descent is an optimization algorithm",
        "retrieved_contexts": "Gradient Descent is a method for minimizing…",
    }
    with patch("app.api.v1.evaluate.persist_eval_result", new_callable=AsyncMock):
        with patch(
            "app.evaluators.llm_judge.Faithfulness.call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            stmt_resp = MagicMock()
            stmt_resp.choices = [
                MagicMock(message=MagicMock(parsed=MagicMock(statements=["stmt1", "stmt2"])))
            ]
            verdict_resp = MagicMock()
            verdict_resp.choices = [
                MagicMock(
                    message=MagicMock(
                        parsed=MagicMock(
                            statements=[
                                MagicMock(statement="stmt1", reason="ok", verdict=1),
                                MagicMock(statement="stmt2", reason="no", verdict=0),
                            ]
                        )
                    )
                )
            ]
            mock_llm.side_effect = [stmt_resp, verdict_resp]

            async with async_client as client:
                resp = await client.post("/api/v1/evaluation/llm_judge/faithfulness", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["eval_id"] == eval_id
    assert body["status"] == "success"
    # result section
    assert body["result"]["score"] == 0.5
    assert "reason" in body["result"]
    # metadata section
    assert body["metadata"]["evaluator_type"] == "llm_judge"
    assert body["metadata"]["metric_name"] == "faithfulness"
    assert body["metadata"]["eval_latency_s"] >= 0
    assert "evaluated_at" in body["metadata"]


# ── Validation errors (Pydantic catches these before handler) ──────────────────

async def test_faithfulness_missing_response_returns_422(async_client, eval_id):
    payload = {
        "eval_id": eval_id,
        "retrieved_contexts": "some context",
    }
    async with async_client as client:
        resp = await client.post("/api/v1/evaluation/llm_judge/faithfulness", json=payload)
    assert resp.status_code == 422
    assert any("response" in str(e) for e in resp.json()["detail"])


async def test_factual_correctness_without_reference_returns_422(async_client, eval_id):
    payload = {
        "eval_id": eval_id,
        "response": "some text",
    }
    async with async_client as client:
        resp = await client.post("/api/v1/evaluation/llm_judge/factual_correctness", json=payload)
    assert resp.status_code == 422
    assert any("reference" in str(e) for e in resp.json()["detail"])


async def test_auto_generated_eval_id(async_client):
    """eval_id is optional — service generates one if not provided."""
    payload = {
        "response": "some text",
        "retrieved_contexts": "some context",
    }
    with patch("app.api.v1.evaluate.persist_eval_result", new_callable=AsyncMock):
        with patch(
            "app.evaluators.llm_judge.Faithfulness.call_llm",
            new_callable=AsyncMock,
        ) as mock_llm:
            stmt_resp = MagicMock()
            stmt_resp.choices = [
                MagicMock(message=MagicMock(parsed=MagicMock(statements=["stmt1"])))
            ]
            verdict_resp = MagicMock()
            verdict_resp.choices = [
                MagicMock(
                    message=MagicMock(
                        parsed=MagicMock(
                            statements=[MagicMock(statement="stmt1", reason="ok", verdict=1)]
                        )
                    )
                )
            ]
            mock_llm.side_effect = [stmt_resp, verdict_resp]

            async with async_client as client:
                resp = await client.post("/api/v1/evaluation/llm_judge/faithfulness", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["eval_id"] is not None
    assert body["status"] == "success"


# ── LLM error paths ────────────────────────────────────────────────────────────

async def test_rate_limit_returns_503(async_client, eval_id):
    import openai

    payload = {
        "eval_id": eval_id,
        "response": "some text",
        "retrieved_contexts": "some context",
    }
    with (
        patch("app.api.v1.evaluate.persist_eval_result", new_callable=AsyncMock),
        patch(
            "app.evaluators.llm_judge.Faithfulness.call_llm",
            new_callable=AsyncMock,
            side_effect=openai.RateLimitError("rate limit", response=MagicMock(), body={}),
        ),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        async with async_client as client:
            resp = await client.post("/api/v1/evaluation/llm_judge/faithfulness", json=payload)

    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"]["error"] == "LLM_RATE_LIMIT"


async def test_timeout_returns_504(async_client, eval_id):
    import openai

    payload = {
        "eval_id": eval_id,
        "response": "some text",
        "retrieved_contexts": "some context",
    }
    with (
        patch("app.api.v1.evaluate.persist_eval_result", new_callable=AsyncMock),
        patch(
            "app.evaluators.llm_judge.Faithfulness.call_llm",
            new_callable=AsyncMock,
            side_effect=openai.APITimeoutError("timeout"),
        ),
    ):
        async with async_client as client:
            resp = await client.post("/api/v1/evaluation/llm_judge/faithfulness", json=payload)

    assert resp.status_code == 504
    body = resp.json()
    assert body["detail"]["error"] == "LLM_TIMEOUT"
