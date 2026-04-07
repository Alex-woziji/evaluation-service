"""Application-wide logger factory with request ID support."""

import logging
import sys
from typing import Optional

from contextvars import ContextVar

# Per-request trace ID, set at request entry point
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def get_request_id() -> Optional[str]:
    return _request_id.get()


class _Formatter(logging.Formatter):
    """Human-readable formatter with optional request_id."""

    _base = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    _with_rid = "%(asctime)s | %(levelname)-7s | %(name)s | [%(rid)s] %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        rid = get_request_id()
        if rid:
            record.rid = rid  # type: ignore[attr-defined]
            self._fmt = self._with_rid
        else:
            self._fmt = self._base
        return super().format(record)


_initialized = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger; configures root handler once."""
    global _initialized
    if not _initialized:
        _initialized = True
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_Formatter(datefmt="%Y-%m-%d %H:%M:%S"))
        root = logging.getLogger()
        root.addHandler(handler)
        # Suppress noisy third-party loggers
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger = logging.getLogger(name)
    return logger
