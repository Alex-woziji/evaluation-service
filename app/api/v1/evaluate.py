from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

from app.evaluators import llm_judge_evaluator  # noqa: F401 — ensure registration
from app.evaluators.base import EvalConfig, EvalRecord
from app.evaluators.registry import registry
from app.exceptions import (
    ConfigValidationError,
    LLMAPIError,
    LLMTimeoutError,
    ParseError,
)
from app.models.request import EvaluateRequest
from app.models.response import ErrorResponse, EvaluateResponse, ValidationErrorDetail
from app.tasks.persist import persist_eval_result

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/evaluation")


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(
    request: EvaluateRequest,
    background_tasks: BackgroundTasks,
) -> EvaluateResponse:
    # ── 1. Resolve evaluator ──────────────────────────────────────────────────
    evaluator = registry.get(request.metric_type)
    if evaluator is None:
        raise HTTPException(
            status_code=422,
            detail=ErrorResponse(
                error="UNKNOWN_METRIC_TYPE",
                message=f"metric_type '{request.metric_type}' is not registered",
            ).model_dump(),
        )

    # ── 2. Build internal dataclasses ─────────────────────────────────────────
    record = EvalRecord(
        input=request.record.input,
        output=request.record.output,
        reference=request.record.reference,
        metadata=request.record.metadata,
    )

    # Collect extra fields from EvalConfigIn (Pydantic "extra": "allow")
    config_data = request.eval_config.model_dump()
    extra = {
        k: v
        for k, v in config_data.items()
        if k not in {"judge_model", "criteria", "rubric", "score_range", "language"}
    }
    config = EvalConfig(
        judge_model=request.eval_config.judge_model or "",
        criteria=request.eval_config.criteria,
        rubric=request.eval_config.rubric,
        score_range=request.eval_config.score_range,
        language=request.eval_config.language,
        extra=extra,
    )

    # ── 3. Metric-level config validation ─────────────────────────────────────
    try:
        evaluator.validate_config(config)
    except ConfigValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=ErrorResponse(
                error="CONFIG_VALIDATION_ERROR",
                detail=[
                    ValidationErrorDetail(
                        field=exc.field or "eval_config",
                        message=exc.message,
                    )
                ],
            ).model_dump(),
        )

    # ── 4. Evaluate ───────────────────────────────────────────────────────────
    evaluated_at = datetime.now(tz=timezone.utc)
    try:
        result = await evaluator.evaluate(record, config)
    except ParseError as exc:
        background_tasks.add_task(
            persist_eval_result,
            eval_id=request.eval_id,
            metric_type=request.metric_type,
            status="failed",
            evaluated_at=evaluated_at,
            error_type="PARSE_ERROR",
            error_message=exc.message,
        )
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="PARSE_ERROR",
                message=exc.message,
                eval_id=request.eval_id,
            ).model_dump(),
        )
    except LLMTimeoutError as exc:
        background_tasks.add_task(
            persist_eval_result,
            eval_id=request.eval_id,
            metric_type=request.metric_type,
            status="failed",
            evaluated_at=evaluated_at,
            error_type="LLM_TIMEOUT",
            error_message=exc.message,
            retry_count=exc.retry_count,
        )
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="LLM_TIMEOUT",
                message=exc.message,
                retry_count=exc.retry_count,
                eval_id=request.eval_id,
            ).model_dump(),
        )
    except LLMAPIError as exc:
        background_tasks.add_task(
            persist_eval_result,
            eval_id=request.eval_id,
            metric_type=request.metric_type,
            status="failed",
            evaluated_at=evaluated_at,
            error_type="LLM_API_ERROR",
            error_message=exc.message,
            retry_count=exc.retry_count,
        )
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="LLM_API_ERROR",
                message=exc.message,
                retry_count=exc.retry_count,
                eval_id=request.eval_id,
            ).model_dump(),
        )
    except Exception as exc:
        logger.exception("Unexpected error for eval_id=%s", request.eval_id)
        background_tasks.add_task(
            persist_eval_result,
            eval_id=request.eval_id,
            metric_type=request.metric_type,
            status="failed",
            evaluated_at=evaluated_at,
            error_type="INTERNAL_ERROR",
            error_message=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="INTERNAL_ERROR",
                message="An unexpected error occurred",
                eval_id=request.eval_id,
            ).model_dump(),
        )

    # ── 5. Schedule background persistence ───────────────────────────────────
    background_tasks.add_task(
        persist_eval_result,
        eval_id=request.eval_id,
        metric_type=request.metric_type,
        status="success",
        evaluated_at=evaluated_at,
        score=result.score,
        scores_detail=result.scores_detail,
        reasoning=result.reasoning,
        retry_count=result.retry_count,
        eval_latency_ms=result.eval_latency_ms,
        llm_call_data=result.llm_call_data,
    )

    # ── 6. Return response ────────────────────────────────────────────────────
    return EvaluateResponse(
        eval_id=request.eval_id,
        metric_type=request.metric_type,
        status="success",
        score=result.score,
        scores_detail=result.scores_detail,
        reasoning=result.reasoning,
        raw_output=result.raw_output,
        retry_count=result.retry_count,
        eval_latency_ms=result.eval_latency_ms,
        evaluated_at=evaluated_at,
    )


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "registered_evaluators": registry.list_registered(),
        "version": "1.0.0",
    }
