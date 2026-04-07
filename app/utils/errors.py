"""Centralised error codes and HTTP status mapping."""

from enum import Enum


class ErrorCode(str, Enum):
    """Application-level error codes with associated HTTP status."""

    LLM_AUTH_ERROR = "LLM_AUTH_ERROR"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_BAD_REQUEST = "LLM_BAD_REQUEST"
    METRIC_ERROR = "METRIC_ERROR"
    UNKNOWN_METRIC = "UNKNOWN_METRIC"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS_MAP[self]


_HTTP_STATUS_MAP: dict[ErrorCode, int] = {
    ErrorCode.LLM_AUTH_ERROR: 500,
    ErrorCode.LLM_RATE_LIMIT: 503,
    ErrorCode.LLM_TIMEOUT: 504,
    ErrorCode.LLM_BAD_REQUEST: 400,
    ErrorCode.METRIC_ERROR: 422,
    ErrorCode.UNKNOWN_METRIC: 422,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.INTERNAL_ERROR: 500,
}
