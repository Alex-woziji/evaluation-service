from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.db.connection import AsyncSessionLocal
from app.db.evaluation_result_repo import upsert_evaluation_result
from app.db.models import LLMMetadata
from app.utils.llm_tracker import LLMCallRecord

logger = logging.getLogger(__name__)


async def persist_eval_result(
    eval_id: UUID,
    evaluator_type: str,
    metric_name: str,
    status: str,
    evaluated_at: datetime,
    task_id: Optional[str] = None,
    score: Optional[float] = None,
    reason: Optional[Any] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    eval_latency_s: Optional[float] = None,
    llm_calls: Optional[list[LLMCallRecord]] = None,
) -> None:
    """Background task: write evaluation_result and llm_metadata.

    Any exception is caught, logged, and swallowed — must never affect the HTTP response.
    """
    try:
        async with AsyncSessionLocal() as session:
            await upsert_evaluation_result(
                session=session,
                eval_id=eval_id,
                metric_type=evaluator_type,
                metric_name=metric_name,
                status=status,
                evaluated_at=evaluated_at,
                task_id=task_id,
                score=score,
                reason=reason,
                error_type=error_type,
                error_message=error_message,
                eval_latency_s=eval_latency_s,
            )

            if llm_calls:
                eval_id_str = str(eval_id)
                for call in llm_calls:
                    session.add(
                        LLMMetadata(
                            evaluation_result_id=eval_id_str,
                            judge_model=call.model,
                            messages=call.messages,
                            raw_response=call.raw_response,
                            input_tokens=call.input_tokens,
                            output_tokens=call.output_tokens,
                            llm_latency_s=call.latency_s,
                            attempt_number=call.attempt_number,
                        )
                    )

            await session.commit()

    except Exception:
        logger.exception(
            "Background persist failed for eval_id=%s metric=%s/%s",
            eval_id,
            evaluator_type,
            metric_name,
        )
