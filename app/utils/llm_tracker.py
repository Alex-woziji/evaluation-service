from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMCallRecord:
    """Metadata captured for a single successful LLM API call."""

    model: str
    messages: list[dict[str, str]]
    raw_response: dict[str, Any] | None
    input_tokens: int | None
    output_tokens: int | None
    latency_s: float
    attempt_number: int


_llm_calls: ContextVar[list[LLMCallRecord] | None] = ContextVar("llm_calls", default=None)


def start_tracking() -> None:
    """Start recording LLM calls for the current async context."""
    _llm_calls.set([])


def record_call(record: LLMCallRecord) -> None:
    """Append a call record if tracking is active."""
    calls = _llm_calls.get()
    if calls is not None:
        calls.append(record)


def get_tracked_calls() -> list[LLMCallRecord]:
    """Return all tracked calls and stop tracking."""
    calls = _llm_calls.get()
    _llm_calls.set(None)
    return list(calls) if calls is not None else []
