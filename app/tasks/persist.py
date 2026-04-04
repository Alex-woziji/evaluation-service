from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from app.db.connection import AsyncSessionLocal
from app.db.eval_log_repo import upsert_eval_log

logger = logging.getLogger(__name__)


async def persist_eval_result(
    eval_id: UUID,
    evaluator_type: str,
    metric_name: str,
    status: str,
    evaluated_at: datetime,
    score: Optional[float] = None,
    detail: Optional[Dict[str, Any]] = None,
    reasoning: Optional[str] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    eval_latency_s: Optional[float] = None,
) -> None:
    """Background task: write eval_log.

    Any exception is caught, logged, and swallowed — must never affect the HTTP response.
    """
    try:
        async with AsyncSessionLocal() as session:
            await upsert_eval_log(
                session=session,
                eval_id=eval_id,
                metric_type=evaluator_type,
                metric_name=metric_name,
                status=status,
                evaluated_at=evaluated_at,
                score=score,
                detail=detail,
                reasoning=reasoning,
                error_type=error_type,
                error_message=error_message,
                eval_latency_s=eval_latency_s,
            )
    except Exception:
        logger.exception(
            "Background persist failed for eval_id=%s metric=%s/%s",
            eval_id,
            evaluator_type,
            metric_name,
        )
