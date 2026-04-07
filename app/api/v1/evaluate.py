import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

import openai
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.evaluators import evaluator_registry  # noqa: F401 — ensure registration
from app.models.request import BatchEvaluateRequest, LLMConfig, ValidationErrorDetail
from app.models.response import (
    BatchEvaluateResponse,
    BatchItemResult,
    ErrorResponse,
    EvalMetadata,
    EvaluateResponse,
    MetricResult,
)
from app.tasks.persist import persist_eval_result
from app.utils.config import app_settings
from app.utils.errors import ErrorCode
from app.utils.llm_tracker import get_tracked_calls, set_config_override, start_tracking
from app.utils.logger import get_logger, set_request_id

# Exception → ErrorCode
_EXCEPTION_ERROR_MAP: dict[type[Exception], ErrorCode] = {
    openai.AuthenticationError: ErrorCode.LLM_AUTH_ERROR,
    openai.RateLimitError: ErrorCode.LLM_RATE_LIMIT,
    openai.APITimeoutError: ErrorCode.LLM_TIMEOUT,
    openai.BadRequestError: ErrorCode.LLM_BAD_REQUEST,
}

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/evaluation")


def _make_error(status_code: int, error: str, message: str, eval_id=None, detail=None):
    body = ErrorResponse(error=error, message=message, eval_id=eval_id, detail=detail)
    raise HTTPException(status_code=status_code, detail=body.model_dump(mode="json"))


# ── Core evaluation logic (shared by single + batch) ──────────────────────────

async def _evaluate_single(
    evaluator_type: str,
    metric_name: str,
    eval_id: UUID,
    record: dict,
    background_tasks: BackgroundTasks,
    task_id: Optional[str] = None,
    llm_config: Optional[LLMConfig] = None,
) -> BatchItemResult:
    """Run one metric evaluation. Always returns a result, never raises."""
    evaluated_at = datetime.now(tz=timezone.utc)
    set_request_id(str(eval_id))
    logger.info("metric=%s eval_id=%s — starting evaluation", metric_name, eval_id)

    # ── 1. Resolve ──────────────────────────────────────────────────────────
    try:
        sub = evaluator_registry.get_sub_registry(evaluator_type)
        metric = sub.get(metric_name)
    except KeyError:
        return BatchItemResult(
            eval_id=eval_id, metric_name=metric_name, status="failed",
            error=ErrorCode.UNKNOWN_METRIC, message=f"metric '{metric_name}' not found",
        )

    # ── 2. Evaluate ─────────────────────────────────────────────────────────
    start = time.monotonic()
    start_tracking()
    set_config_override(llm_config)
    try:
        result = await metric.evaluate(**record)
    except Exception as exc:
        error_code = ErrorCode.INTERNAL_ERROR
        for exc_type, code in _EXCEPTION_ERROR_MAP.items():
            if isinstance(exc, exc_type):
                error_code = code
                break
        if isinstance(exc, ValueError):
            error_code = ErrorCode.METRIC_ERROR
        if error_code == ErrorCode.INTERNAL_ERROR:
            logger.exception("Unexpected error for eval_id=%s", eval_id)
        msg = "An unexpected error occurred" if error_code == ErrorCode.INTERNAL_ERROR else str(exc)
        _persist_failure(background_tasks, eval_id, evaluator_type, metric_name, evaluated_at, error_code, str(exc), task_id=task_id)
        return BatchItemResult(eval_id=eval_id, metric_name=metric_name, status="failed", error=error_code, message=msg)
    finally:
        set_config_override(None)

    latency_s = round(time.monotonic() - start, 3)
    llm_calls = get_tracked_calls()

    # ── 3. Build result ─────────────────────────────────────────────────────
    result_data = result if isinstance(result, dict) else {}
    score = result_data.get("score")
    reason = result_data.get("reason")

    logger.info("metric=%s eval_id=%s score=%s latency=%.3fs llm_calls=%d",
                metric_name, eval_id, score, latency_s, len(llm_calls))

    # ── 4. Persist ──────────────────────────────────────────────────────────
    background_tasks.add_task(
        persist_eval_result,
        eval_id=eval_id,
        evaluator_type=evaluator_type,
        metric_name=metric_name,
        status="success",
        evaluated_at=evaluated_at,
        task_id=task_id,
        score=score,
        reason=reason,
        eval_latency_s=latency_s,
        llm_calls=llm_calls,
    )

    # ── 5. Return ───────────────────────────────────────────────────────────
    return BatchItemResult(
        eval_id=eval_id,
        metric_name=metric_name,
        status="success",
        result=MetricResult(score=score, reason=reason, **{k: v for k, v in result_data.items() if k not in ("score", "reason")}),
        metadata=EvalMetadata(
            evaluator_type=evaluator_type,
            metric_name=metric_name,
            eval_latency_s=latency_s,
            evaluated_at=evaluated_at,
        ),
    )


def _persist_failure(
    background_tasks: BackgroundTasks,
    eval_id: UUID,
    evaluator_type: str,
    metric_name: str,
    evaluated_at: datetime,
    error_type: str,
    error_message: str,
    task_id: Optional[str] = None,
) -> None:
    background_tasks.add_task(
        persist_eval_result,
        eval_id=eval_id,
        evaluator_type=evaluator_type,
        metric_name=metric_name,
        status="failed",
        evaluated_at=evaluated_at,
        task_id=task_id,
        error_type=error_type,
        error_message=error_message,
    )


# ── Single-metric routes (per-metric, for Swagger / single calls) ─────────────

def _build_handler(eval_type: str, metric_name: str, req_model):
    """Create a route handler that uses the metric's own request model."""

    async def handler(request: req_model, background_tasks: BackgroundTasks) -> EvaluateResponse:  # type: ignore[valid-type]
        data = request.model_dump(exclude_none=True)
        eval_id = data.pop("eval_id")
        data.pop("llm_config", None)
        item = await _evaluate_single(eval_type, metric_name, eval_id, data, background_tasks, llm_config=request.llm_config)

        if item.status == "failed":
            code = ErrorCode(item.error) if isinstance(item.error, str) else item.error
            _make_error(
                code.http_status,
                item.error, item.message, eval_id=eval_id,
            )

        return EvaluateResponse(
            eval_id=item.eval_id, status=item.status,
            result=item.result, metadata=item.metadata,
        )

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


# ── Batch endpoint ────────────────────────────────────────────────────────────

def _extract_metric_fields(metric, test_case: dict) -> dict:
    """Extract fields required by a metric from the loose test_case dict."""
    fields: dict = {}
    for f in metric.required_fields:
        fields[f] = test_case[f]
    optional = getattr(metric, "optional_fields", [])
    for f in optional:
        if f in test_case:
            fields[f] = test_case[f]
    return fields


@router.post(
    "/batch",
    response_model=BatchEvaluateResponse,
    summary="Batch evaluate multiple metrics concurrently",
    tags=["batch"],
)
async def batch_evaluate(
    request: BatchEvaluateRequest,
    background_tasks: BackgroundTasks,
) -> BatchEvaluateResponse:
    task_id = str(request.task_id)
    test_case = request.test_case

    # ── 1. Resolve all metrics & extract fields ─────────────────────────────
    resolved: list[tuple[str, str, dict]] = []  # (evaluator_type, metric_name, record)
    errors: list[ValidationErrorDetail] = []

    for name in request.metrics:
        try:
            eval_type, metric = evaluator_registry.find_metric(name)
        except KeyError:
            errors.append(ValidationErrorDetail(field="metrics", message=f"Unknown metric '{name}'"))
            continue

        # Check required fields
        missing = [f for f in metric.required_fields if f not in test_case]
        if missing:
            errors.append(ValidationErrorDetail(
                field=name,
                message=f"Missing required fields: {missing}",
            ))
            continue

        resolved.append((eval_type, name, _extract_metric_fields(metric, test_case)))

    if errors:
        _make_error(422, ErrorCode.VALIDATION_ERROR, "Invalid metrics or missing fields", detail=errors)

    # ── 2. Run all metrics concurrently (with concurrency cap) ───────────────
    sem = asyncio.Semaphore(app_settings.batch_max_concurrency)

    async def _run_one(eval_type: str, metric_name: str, record: dict) -> BatchItemResult:
        async with sem:
            return await _evaluate_single(
                evaluator_type=eval_type,
                metric_name=metric_name,
                eval_id=uuid4(),
                record=record,
                background_tasks=background_tasks,
                task_id=task_id,
                llm_config=request.llm_config,
            )

    results = await asyncio.gather(
        *[_run_one(t, n, r) for t, n, r in resolved]
    )

    return BatchEvaluateResponse(task_id=task_id, results=list(results))


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict:
    metrics_info = {}
    for eval_type in evaluator_registry.list_types():
        metrics_info[eval_type] = evaluator_registry.list_metrics(eval_type)
    return {
        "status": "ok",
        "evaluators": metrics_info,
        "version": app_settings.app_version,
    }
