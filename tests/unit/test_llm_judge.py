"""
Unit tests for LLMJudgeEvaluator.
All OpenAI API calls are mocked — no network required.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.evaluators.base import EvalConfig, EvalRecord
from app.evaluators.llm_judge_evaluator import LLMJudgeEvaluator
from app.exceptions import ConfigValidationError, LLMAPIError, LLMTimeoutError, ParseError, RecordValidationError


@pytest.fixture
def evaluator() -> LLMJudgeEvaluator:
    return LLMJudgeEvaluator()


@pytest.fixture
def valid_config() -> EvalConfig:
    return EvalConfig(
        judge_model="gpt-4o",
        criteria=["accuracy", "completeness", "clarity"],
    )


@pytest.fixture
def record() -> dict:
    return {
        "input": "请解释什么是梯度下降",
        "output": "梯度下降是一种优化算法...",
        "reference": "梯度下降（Gradient Descent）是...",
    }


# ── validate_record ─────────────────────────────────────────────────────────────

class TestValidateRecord:
    def test_valid_record_passes(self, evaluator, valid_config, record):
        evaluator.validate_record(record, valid_config)

    def test_missing_input_raises(self, evaluator, valid_config, record):
        del record["input"]
        with pytest.raises(RecordValidationError) as exc:
            evaluator.validate_record(record, valid_config)
        assert exc.value.field == "record.input"

    def test_empty_input_raises(self, evaluator, valid_config, record):
        record["input"] = ""
        with pytest.raises(RecordValidationError) as exc:
            evaluator.validate_record(record, valid_config)
        assert exc.value.field == "record.input"

    def test_missing_output_raises(self, evaluator, valid_config, record):
        del record["output"]
        with pytest.raises(RecordValidationError) as exc:
            evaluator.validate_record(record, valid_config)
        assert exc.value.field == "record.output"

    def test_accuracy_without_reference_raises(self, evaluator, record):
        config = EvalConfig(
            judge_model="gpt-4o",
            criteria=["accuracy"],
        )
        record.pop("reference", None)
        with pytest.raises(RecordValidationError) as exc:
            evaluator.validate_record(record, config)
        assert exc.value.field == "record.reference"
        assert "accuracy" in exc.value.message

    def test_accuracy_with_empty_reference_raises(self, evaluator, record):
        config = EvalConfig(
            judge_model="gpt-4o",
            criteria=["accuracy"],
        )
        record["reference"] = "  "
        with pytest.raises(RecordValidationError) as exc:
            evaluator.validate_record(record, config)
        assert exc.value.field == "record.reference"

    def test_completeness_without_reference_passes(self, evaluator, record):
        config = EvalConfig(
            judge_model="gpt-4o",
            criteria=["completeness", "clarity"],
        )
        record.pop("reference", None)
        evaluator.validate_record(record, config)

    def test_non_string_input_raises(self, evaluator, valid_config, record):
        record["input"] = 123
        with pytest.raises(RecordValidationError) as exc:
            evaluator.validate_record(record, valid_config)
        assert exc.value.field == "record.input"


# ── validate_config ────────────────────────────────────────────────────────────

class TestValidateConfig:
    def test_valid_config_passes(self, evaluator, valid_config):
        evaluator.validate_config(valid_config)  # should not raise

    def test_missing_judge_model_raises(self, evaluator, valid_config):
        valid_config.judge_model = ""
        with pytest.raises(ConfigValidationError) as exc:
            evaluator.validate_config(valid_config)
        assert exc.value.field == "eval_config.judge_model"

    def test_empty_criteria_raises(self, evaluator, valid_config):
        valid_config.criteria = []
        with pytest.raises(ConfigValidationError) as exc:
            evaluator.validate_config(valid_config)
        assert exc.value.field == "eval_config.criteria"

    def test_blank_criterion_raises(self, evaluator, valid_config):
        valid_config.criteria = ["accuracy", "  "]
        with pytest.raises(ConfigValidationError) as exc:
            evaluator.validate_config(valid_config)
        assert exc.value.field == "eval_config.criteria"

    def test_invalid_score_range_raises(self, evaluator, valid_config):
        valid_config.score_range = {"min": 1.0, "max": 0.5}
        with pytest.raises(ConfigValidationError) as exc:
            evaluator.validate_config(valid_config)
        assert exc.value.field == "eval_config.score_range"


# ── evaluate — success path ────────────────────────────────────────────────────

def _mock_openai_response(criteria_scores: dict, reasoning: str = "looks good"):
    content = json.dumps({"criteria_scores": criteria_scores, "reasoning": reasoning})
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.model_dump.return_value = {"mocked": True}
    return response


@pytest.mark.asyncio
class TestEvaluateSuccess:
    async def test_returns_eval_result(self, evaluator, valid_config):
        record = EvalRecord(
            input="请解释什么是梯度下降",
            output="梯度下降是一种优化算法...",
            reference="梯度下降（Gradient Descent）是...",
        )
        mock_resp = _mock_openai_response(
            {"accuracy": 0.9, "completeness": 0.8, "clarity": 0.85}
        )
        with patch(
            "app.evaluators.llm_judge_evaluator.AsyncOpenAI"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client

            result = await evaluator.evaluate(record, valid_config)

        assert result.score == pytest.approx((0.9 + 0.8 + 0.85) / 3, abs=1e-6)
        assert result.scores_detail == {"accuracy": 0.9, "completeness": 0.8, "clarity": 0.85}
        assert result.reasoning == "looks good"
        assert result.retry_count == 0
        assert result.llm_call_data is not None
        assert len(result.llm_call_data) == 1
        assert result.llm_call_data[0]["attempt_number"] == 1

    async def test_scores_clamped_to_0_1(self, evaluator, valid_config):
        record = EvalRecord(
            input="请解释什么是梯度下降",
            output="梯度下降是一种优化算法...",
            reference="梯度下降（Gradient Descent）是...",
        )
        mock_resp = _mock_openai_response({"accuracy": 1.5, "completeness": -0.2})
        with patch("app.evaluators.llm_judge_evaluator.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
            mock_cls.return_value = mock_client
            result = await evaluator.evaluate(record, valid_config)

        assert all(0.0 <= v <= 1.0 for v in result.scores_detail.values())
        assert 0.0 <= result.score <= 1.0


# ── evaluate — retry logic ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestEvaluateRetry:
    async def test_retries_on_rate_limit_then_succeeds(self, evaluator, valid_config):
        import openai
        record = EvalRecord(
            input="请解释什么是梯度下降",
            output="梯度下降是一种优化算法...",
            reference="梯度下降（Gradient Descent）是...",
        )
        mock_resp = _mock_openai_response({"accuracy": 0.9})
        side_effects = [
            openai.RateLimitError("rate limit", response=MagicMock(), body={}),
            mock_resp,
        ]
        with patch("app.evaluators.llm_judge_evaluator.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=side_effects)
            mock_cls.return_value = mock_client
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await evaluator.evaluate(record, valid_config)

        assert result.retry_count == 1
        assert len(result.llm_call_data) == 2

    async def test_raises_llm_api_error_after_max_retries(self, evaluator, valid_config):
        import openai
        record = EvalRecord(
            input="请解释什么是梯度下降",
            output="梯度下降是一种优化算法...",
        )
        with patch("app.evaluators.llm_judge_evaluator.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=openai.RateLimitError("rate limit", response=MagicMock(), body={})
            )
            mock_cls.return_value = mock_client
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(LLMAPIError) as exc:
                    await evaluator.evaluate(record, valid_config)
        assert exc.value.retry_count == 2

    async def test_raises_llm_timeout_after_max_retries(self, evaluator, valid_config):
        import openai
        record = EvalRecord(
            input="请解释什么是梯度下降",
            output="梯度下降是一种优化算法...",
        )
        with patch("app.evaluators.llm_judge_evaluator.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=openai.APITimeoutError(request=MagicMock())
            )
            mock_cls.return_value = mock_client
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(LLMTimeoutError) as exc:
                    await evaluator.evaluate(record, valid_config)
        assert exc.value.retry_count == 2

    async def test_no_retry_on_parse_error(self, evaluator, valid_config):
        record = EvalRecord(
            input="请解释什么是梯度下降",
            output="梯度下降是一种优化算法...",
        )
        bad_content = "not json at all"
        message = MagicMock()
        message.content = bad_content
        choice = MagicMock()
        choice.message = message
        usage = MagicMock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 5
        response = MagicMock()
        response.choices = [choice]
        response.usage = usage
        response.model_dump.return_value = {}

        with patch("app.evaluators.llm_judge_evaluator.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=response)
            mock_cls.return_value = mock_client
            with pytest.raises(ParseError):
                await evaluator.evaluate(record, valid_config)

        # Only 1 call — no retry after parse error
        assert mock_client.chat.completions.create.call_count == 1

    async def test_no_retry_on_auth_error(self, evaluator, valid_config):
        import openai
        record = EvalRecord(
            input="请解释什么是梯度下降",
            output="梯度下降是一种优化算法...",
        )
        with patch("app.evaluators.llm_judge_evaluator.AsyncOpenAI") as mock_cls:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=openai.AuthenticationError(
                    "auth failed", response=MagicMock(), body={}
                )
            )
            mock_cls.return_value = mock_client
            with pytest.raises(LLMAPIError):
                await evaluator.evaluate(record, valid_config)

        assert mock_client.chat.completions.create.call_count == 1
