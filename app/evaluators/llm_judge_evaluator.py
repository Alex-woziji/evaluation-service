from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional

import openai
from openai import AsyncOpenAI

from app.evaluators.base import BaseEvaluator, EvalConfig, EvalRecord, EvalResult
from app.evaluators.registry import registry
from app.exceptions import ConfigValidationError, LLMAPIError, LLMTimeoutError, ParseError

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = """\
You are a rigorous LLM output evaluator. Evaluate the provided model output against the given criteria.
Return a JSON object with the following structure (no markdown, raw JSON only):
{{
  "criteria_scores": {{"criterion_name": score_between_0_and_1, ...}},
  "reasoning": "concise explanation of the scores"
}}
All scores must be floats between 0.0 and 1.0.\
"""

_DEFAULT_USER_PROMPT_TEMPLATE = """\
## Task
Evaluate the following model output.

## Input (what was sent to the model)
{input}

## Model Output (what you are evaluating)
{output}
{reference_section}
## Evaluation Criteria
{criteria_list}
{rubric_section}
## Instructions
Score each criterion independently on a scale from 0.0 to 1.0.
Respond with raw JSON only — no markdown fences.\
"""


def _build_prompts(record: EvalRecord, config: EvalConfig) -> tuple[str, str]:
    reference_section = (
        f"\n## Reference Answer\n{record.reference}\n" if record.reference else ""
    )
    criteria_list = "\n".join(f"- {c}" for c in config.criteria)
    rubric_section = f"\n## Scoring Rubric\n{config.rubric}\n" if config.rubric else ""

    user_prompt = _DEFAULT_USER_PROMPT_TEMPLATE.format(
        input=record.input,
        output=record.output,
        reference_section=reference_section,
        criteria_list=criteria_list,
        rubric_section=rubric_section,
    )
    return _DEFAULT_SYSTEM_PROMPT, user_prompt


def _normalize_score(raw_score: float, score_range: Dict[str, float]) -> float:
    """Clamp raw score to [0,1] regardless of score_range (scores are already 0-1)."""
    return max(0.0, min(1.0, raw_score))


def _parse_llm_response(content: str) -> tuple[Dict[str, float], str]:
    """Parse LLM JSON response. Raises ParseError on failure."""
    try:
        # Strip markdown code fences if present
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(stripped)
        criteria_scores: Dict[str, float] = {}
        for k, v in data.get("criteria_scores", {}).items():
            criteria_scores[k] = float(v)
        reasoning: str = data.get("reasoning", "")
        if not criteria_scores:
            raise ParseError("LLM returned empty criteria_scores", raw_response=content)
        return criteria_scores, reasoning
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ParseError(f"Failed to parse LLM response: {exc}", raw_response=content) from exc


@registry.register
class LLMJudgeEvaluator(BaseEvaluator):
    metric_type = "llm_judge"

    _MAX_ATTEMPTS = 3
    _BASE_WAIT = 2.0  # seconds, exponential base
    _MAX_WAIT = 10.0  # seconds cap
    _JITTER = 0.5  # ±0.5s

    def validate_config(self, config: EvalConfig) -> None:
        if not config.judge_model:
            raise ConfigValidationError(
                "judge_model is required for llm_judge", field="eval_config.judge_model"
            )
        if not config.criteria:
            raise ConfigValidationError(
                "criteria must be a non-empty list for llm_judge", field="eval_config.criteria"
            )
        for item in config.criteria:
            if not isinstance(item, str) or not item.strip():
                raise ConfigValidationError(
                    "each criterion must be a non-empty string", field="eval_config.criteria"
                )
        score_range = config.score_range
        if score_range.get("min", 0) >= score_range.get("max", 1):
            raise ConfigValidationError(
                "score_range min must be less than max", field="eval_config.score_range"
            )

    async def evaluate(self, record: EvalRecord, config: EvalConfig) -> EvalResult:
        client = AsyncOpenAI()
        system_prompt, user_prompt = _build_prompts(record, config)

        llm_call_data: List[Dict[str, Any]] = []
        last_error: Optional[Exception] = None
        total_start = time.monotonic()

        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            attempt_start = time.monotonic()
            raw_response_data: Optional[Dict[str, Any]] = None
            input_tokens: Optional[int] = None
            output_tokens: Optional[int] = None

            try:
                response = await client.chat.completions.create(
                    model=config.judge_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )
                llm_latency_ms = int((time.monotonic() - attempt_start) * 1000)
                content = response.choices[0].message.content or ""
                input_tokens = response.usage.prompt_tokens if response.usage else None
                output_tokens = response.usage.completion_tokens if response.usage else None
                raw_response_data = response.model_dump()

                llm_call_data.append(
                    {
                        "judge_model": config.judge_model,
                        "prompt_system": system_prompt,
                        "prompt_user": user_prompt,
                        "raw_response": raw_response_data,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "llm_latency_ms": llm_latency_ms,
                        "attempt_number": attempt,
                    }
                )

                # May raise ParseError (no retry)
                criteria_scores, reasoning = _parse_llm_response(content)

                # Normalize scores
                scores_detail = {
                    k: _normalize_score(v, config.score_range)
                    for k, v in criteria_scores.items()
                }
                overall_score = sum(scores_detail.values()) / len(scores_detail)
                overall_score = _normalize_score(overall_score, config.score_range)

                total_latency_ms = int((time.monotonic() - total_start) * 1000)
                return EvalResult(
                    score=overall_score,
                    scores_detail=scores_detail,
                    reasoning=reasoning,
                    raw_output=raw_response_data,
                    retry_count=attempt - 1,
                    eval_latency_ms=total_latency_ms,
                    llm_call_data=llm_call_data,
                )

            except ParseError:
                # Record the call data even on parse failure
                if raw_response_data is not None:
                    llm_call_data.append(
                        {
                            "judge_model": config.judge_model,
                            "prompt_system": system_prompt,
                            "prompt_user": user_prompt,
                            "raw_response": raw_response_data,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "llm_latency_ms": int((time.monotonic() - attempt_start) * 1000),
                            "attempt_number": attempt,
                        }
                    )
                raise  # No retry

            except openai.AuthenticationError as exc:
                raise LLMAPIError(f"Authentication failed: {exc}", retry_count=0) from exc

            except openai.BadRequestError as exc:
                raise LLMAPIError(f"Bad request: {exc}", retry_count=0) from exc

            except (openai.RateLimitError, openai.APITimeoutError) as exc:
                last_error = exc
                llm_call_data.append(
                    {
                        "judge_model": config.judge_model,
                        "prompt_system": system_prompt,
                        "prompt_user": user_prompt,
                        "raw_response": None,
                        "input_tokens": None,
                        "output_tokens": None,
                        "llm_latency_ms": int((time.monotonic() - attempt_start) * 1000),
                        "attempt_number": attempt,
                    }
                )

            except openai.APIStatusError as exc:
                if exc.status_code == 503:
                    last_error = exc
                    llm_call_data.append(
                        {
                            "judge_model": config.judge_model,
                            "prompt_system": system_prompt,
                            "prompt_user": user_prompt,
                            "raw_response": None,
                            "input_tokens": None,
                            "output_tokens": None,
                            "llm_latency_ms": int((time.monotonic() - attempt_start) * 1000),
                            "attempt_number": attempt,
                        }
                    )
                else:
                    raise LLMAPIError(
                        f"LLM API error {exc.status_code}: {exc.message}",
                        retry_count=attempt - 1,
                    ) from exc

            # Backoff before next attempt
            if attempt < self._MAX_ATTEMPTS:
                wait = min(self._BASE_WAIT ** attempt, self._MAX_WAIT)
                jitter = random.uniform(-self._JITTER, self._JITTER)
                await asyncio.sleep(max(0.0, wait + jitter))

        # All attempts exhausted
        retry_count = self._MAX_ATTEMPTS - 1
        if isinstance(last_error, openai.APITimeoutError):
            raise LLMTimeoutError(
                f"LLM timed out after {self._MAX_ATTEMPTS} attempts",
                retry_count=retry_count,
            )
        raise LLMAPIError(
            f"LLM API error after {self._MAX_ATTEMPTS} attempts: {last_error}",
            retry_count=retry_count,
        )
