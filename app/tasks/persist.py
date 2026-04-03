from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.db.connection import AsyncSessionLocal
from app.db.eval_log_repo import upsert_eval_log
from app.db.llm_call_log_repo import insert_llm_call_log

logger = logging.getLogger(__name__)


async def persist_eval_result(
    eval_id: UUID,
    metric_type: str,
    status: str,
    evaluated_at: datetime,
    score: Optional[float] = None,
    scores_detail: Optional[Dict[str, float]] = None,
    reasoning: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    retry_count: int = 0,
    eval_latency_ms: Optional[int] = None,
    llm_call_data: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Background task: write eval_log and (for llm_judge) llm_call_log.
    Any exception is caught, logged, and swallowed — must never affect the HTTP response.
    """
    try:
        async with AsyncSessionLocal() as session:
            await upsert_eval_log(
                session=session,
                eval_id=eval_id,
                metric_type=metric_type,
                status=status,
                evaluated_at=evaluated_at,
                score=score,
                scores_detail=scores_detail,
                reasoning=reasoning,
                error_type=error_type,
                error_message=error_message,
                retry_count=retry_count,
                eval_latency_ms=eval_latency_ms,
            )

        if llm_call_data:
            async with AsyncSessionLocal() as session:
                for call in llm_call_data:
                    await insert_llm_call_log(
                        session=session,
                        eval_log_id=eval_id,
                        judge_model=call.get("judge_model", ""),
                        attempt_number=call.get("attempt_number", 1),
                        prompt_system=call.get("prompt_system"),
                        prompt_user=call.get("prompt_user"),
                        raw_response=call.get("raw_response"),
                        input_tokens=call.get("input_tokens"),
                        output_tokens=call.get("output_tokens"),
                        llm_latency_ms=call.get("llm_latency_ms"),
                    )

    except Exception:
        logger.exception(
            "Background persist failed for eval_id=%s metric_type=%s",
            eval_id,
            metric_type,
        )
