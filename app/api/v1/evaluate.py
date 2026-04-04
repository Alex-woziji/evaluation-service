import time
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

import openai
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.evaluators import evaluator_registry  # noqa: F401 — ensure registration
from app.models.response import ErrorResponse, EvaluateResponse, ValidationErrorDetail
from app.tasks.persist import persist_eval_result
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/evaluation")


def _make_error(status_code: int, error: str, message: str, eval_id=None, detail=None):
    body = ErrorResponse(error=error, message=message, eval_id=eval_id, detail=detail)
    raise HTTPException(status_code=status_code, detail=body.model_dump(mode="json"))


# ── Core handler logic ────────────────────────────────────────────────────────

async def _evaluate(
    evaluator_type: str,
    metric_name: str,
    eval_id: UUID,
    record: dict,
    background_tasks: BackgroundTasks,
) -> EvaluateResponse:
    evaluated_at = datetime.now(tz=timezone.utc)

    # ── 1. Resolve ──────────────────────────────────────────────────────────────
    try:
        sub = evaluator_registry.get_sub_registry(evaluator_type)
        metric = sub.get(metric_name)
    except KeyError:
        _make_error(422, "UNKNOWN_METRIC", f"metric '{metric_name}' not found", eval_id=eval_id)

    # ── 2. Evaluate ─────────────────────────────────────────────────────────────
    start = time.monotonic()
    try:
        result = await metric.evaluate(**record)
    except openai.AuthenticationError as exc:
        _persist_failure(background_tasks, eval_id, evaluator_type, metric_name, evaluated_at, "LLM_AUTH_ERROR", str(exc))
        _make_error(500, "LLM_AUTH_ERROR", str(exc), eval_id=eval_id)
    except openai.RateLimitError as exc:
        _persist_failure(background_tasks, eval_id, evaluator_type, metric_name, evaluated_at, "LLM_RATE_LIMIT", str(exc))
        _make_error(503, "LLM_RATE_LIMIT", str(exc), eval_id=eval_id)
    except openai.APITimeoutError as exc:
        _persist_failure(background_tasks, eval_id, evaluator_type, metric_name, evaluated_at, "LLM_TIMEOUT", str(exc))
        _make_error(504, "LLM_TIMEOUT", str(exc), eval_id=eval_id)
    except openai.BadRequestError as exc:
        _persist_failure(background_tasks, eval_id, evaluator_type, metric_name, evaluated_at, "LLM_BAD_REQUEST", str(exc))
        _make_error(500, "LLM_BAD_REQUEST", str(exc), eval_id=eval_id)
    except ValueError as exc:
        _persist_failure(background_tasks, eval_id, evaluator_type, metric_name, evaluated_at, "METRIC_ERROR", str(exc))
        _make_error(500, "METRIC_ERROR", str(exc), eval_id=eval_id)
    except Exception as exc:
        logger.exception("Unexpected error for eval_id=%s", eval_id)
        _persist_failure(background_tasks, eval_id, evaluator_type, metric_name, evaluated_at, "INTERNAL_ERROR", str(exc))
        _make_error(500, "INTERNAL_ERROR", "An unexpected error occurred", eval_id=eval_id)

    latency_ms = int((time.monotonic() - start) * 1000)

    # ── 3. Extract result ───────────────────────────────────────────────────────
    score = None
    detail = None
    if isinstance(result, dict):
        score = result.get("score")
        detail = {k: v for k, v in result.items() if k != "score"} or None

    # ── 4. Persist ──────────────────────────────────────────────────────────────
    background_tasks.add_task(
        persist_eval_result,
        eval_id=eval_id,
        evaluator_type=evaluator_type,
        metric_name=metric_name,
        status="success",
        evaluated_at=evaluated_at,
        score=score,
        detail=detail,
        eval_latency_ms=latency_ms,
    )

    # ── 5. Respond ──────────────────────────────────────────────────────────────
    return EvaluateResponse(
        eval_id=eval_id,
        evaluator_type=evaluator_type,
        metric_name=metric_name,
        status="success",
        score=score,
        detail=detail,
        eval_latency_ms=latency_ms,
        evaluated_at=evaluated_at,
    )


def _persist_failure(
    background_tasks: BackgroundTasks,
    eval_id: UUID,
    evaluator_type: str,
    metric_name: str,
    evaluated_at: datetime,
    error_type: str,
    error_message: str,
) -> None:
    background_tasks.add_task(
        persist_eval_result,
        eval_id=eval_id,
        evaluator_type=evaluator_type,
        metric_name=metric_name,
        status="failed",
        evaluated_at=evaluated_at,
        error_type=error_type,
        error_message=error_message,
    )


# ── Dynamic route registration ────────────────────────────────────────────────

def _build_handler(eval_type: str, metric_name: str, req_model):
    """Create a route handler that uses the metric's own request model."""

    async def handler(request: req_model, background_tasks: BackgroundTasks) -> EvaluateResponse:  # type: ignore[valid-type]
        data = request.model_dump(exclude_none=True)
        eval_id = data.pop("eval_id")
        return await _evaluate(eval_type, metric_name, eval_id, data, background_tasks)

    handler.__name__ = f"evaluate_{eval_type}_{metric_name}"
    return handler


def _register_metric_routes() -> None:
    """Register one POST route per metric found in evaluator_registry."""
    for eval_type in evaluator_registry.list_types():
        for metric_name in evaluator_registry.list_metrics(eval_type):
            metric = evaluator_registry.get(eval_type, metric_name)
            req_model = metric.request_model

            router.add_api_route(
                f"/{eval_type}/{metric_name}",
                _build_handler(eval_type, metric_name, req_model),
                methods=["POST"],
                response_model=EvaluateResponse,
                summary=f"Evaluate {metric_name}",
                tags=[eval_type],
            )


_register_metric_routes()


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict:
    metrics_info = {}
    for eval_type in evaluator_registry.list_types():
        metrics_info[eval_type] = evaluator_registry.list_metrics(eval_type)
    return {
        "status": "ok",
        "evaluators": metrics_info,
        "version": "2.0.0",
    }
