"""Pure LLM client utilities — no business logic."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import openai
from openai import AsyncAzureOpenAI
from pydantic import BaseModel

from app.utils.config import llm_settings
from app.utils.llm_tracker import LLMCallRecord, get_config_override, record_call
from app.utils.logger import get_logger

logger = get_logger(__name__)


def get_llm_client() -> AsyncAzureOpenAI:
    """Create a new AsyncAzureOpenAI client from environment config.

    Raises
    ------
    ValueError
        If ``AZURE_OPENAI_API_KEY`` or ``AZURE_OPENAI_ENDPOINT`` is missing.
    """
    api_key = llm_settings.AZURE_OPENAI_API_KEY
    endpoint = llm_settings.AZURE_OPENAI_ENDPOINT

    if not api_key or not api_key.strip():
        raise ValueError("AZURE_OPENAI_API_KEY is required but not set")
    if not endpoint or not endpoint.strip():
        raise ValueError("AZURE_OPENAI_ENDPOINT is required but not set")

    return AsyncAzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=llm_settings.AZURE_OPENAI_API_VERSION,
    )


async def call_llm(
    messages: list[dict[str, Any]],
    response_format: dict[str, Any] | type[BaseModel] | None = None,
) -> Any:
    """Send messages to LLM and return the API response. Retry is built-in.

    Parameters
    ----------
    messages : list[dict]
        Chat messages to send.
    response_format : dict | type[BaseModel] | None
        ``{"type": "json_object"}`` for plain JSON, or a Pydantic model class
        for structured output (uses ``parse()`` under the hood).

    Returns
    -------
    Any
        The raw OpenAI chat completion response object.

    Raises
    ------
    openai.AuthenticationError / BadRequestError
        Immediately, no retry.
    openai.APITimeoutError / RateLimitError / APIStatusError(503)
        After all attempts exhausted.
    openai.APIStatusError
        Immediately for non-503 status codes.
    """
    client = get_llm_client()

    # Priority: API param override > env var > default
    override = get_config_override()
    _model = override.model if override and override.model else llm_settings.LLM_MODEL
    _temperature = override.temperature if override and override.temperature is not None else llm_settings.LLM_TEMPERATURE

    kwargs: dict[str, Any] = {
        "model": _model,
        "messages": messages,
        "temperature": _temperature,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    max_attempts = llm_settings.LLM_MAX_ATTEMPTS
    last_error: Exception | None = None

    # Use parse() for pydantic models, create() otherwise
    _is_parse = isinstance(response_format, type) and issubclass(response_format, BaseModel)
    _call = client.chat.completions.parse if _is_parse else client.chat.completions.create

    for attempt in range(1, max_attempts + 1):
        try:
            t0 = time.monotonic()
            response = await _call(**kwargs)
            elapsed = round(time.monotonic() - t0, 3)

            # ── Track call metadata (no-op when not tracking) ──
            raw = {
                "content": response.choices[0].message.content,
                "model": response.model,
                "finish_reason": response.choices[0].finish_reason,
            }
            usage = response.usage
            record_call(LLMCallRecord(
                model=_model,
                messages=messages,
                raw_response=raw,
                input_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.completion_tokens if usage else None,
                latency_s=elapsed,
                attempt_number=attempt,
            ))

            return response

        except openai.AuthenticationError:
            raise
        except openai.BadRequestError:
            raise
        except openai.APIStatusError as exc:
            if exc.status_code != 503:
                raise
            last_error = exc
            logger.warning("Attempt %d/%d failed: APIStatusError 503: %s", attempt, max_attempts, exc)

        except (openai.RateLimitError, openai.APITimeoutError) as exc:
            last_error = exc
            logger.warning("Attempt %d/%d failed: %s: %s", attempt, max_attempts, type(exc).__name__, exc)

        if attempt < max_attempts:
            wait = (
                min(llm_settings.LLM_BASE_WAIT**attempt, llm_settings.LLM_MAX_WAIT)
                + random.uniform(-llm_settings.LLM_JITTER, llm_settings.LLM_JITTER)
            )
            logger.warning(
                "LLM call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt,
                max_attempts,
                wait,
                last_error,
            )
            await asyncio.sleep(max(0.0, wait))

    raise last_error  # type: ignore[misc]


if __name__ == "__main__":
    for setting in llm_settings:
        print(setting)

    async def _test():
        messages = [{"role": "user", "content": "Say hello in JSON: {\"greeting\": \"...\"}"}]
        response = await call_llm(
            messages,
            response_format={"type": "json_object"},
        )
        print(f"Response: {response.choices[0].message.content}")

    asyncio.run(_test())
