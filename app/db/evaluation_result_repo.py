from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvaluationResult

logger = logging.getLogger(__name__)


async def upsert_evaluation_result(
    session: AsyncSession,
    eval_id: UUID,
    metric_type: str,
    status: str,
    evaluated_at: datetime,
    metric_name: Optional[str] = None,
    score: Optional[float] = None,
    reason: Optional[Any] = None,
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    eval_latency_s: Optional[float] = None,
) -> None:
    eval_id_str = str(eval_id)

    existing = await session.get(EvaluationResult, eval_id_str)
    if existing is None:
        session.add(
            EvaluationResult(
                id=eval_id_str,
                metric_type=metric_type,
                metric_name=metric_name,
                status=status,
                score=score,
                reason=reason,
                error_type=error_type,
                error_message=error_message,
                eval_latency_s=eval_latency_s,
                evaluated_at=evaluated_at,
            )
        )
    else:
        existing.metric_type = metric_type
        existing.metric_name = metric_name
        existing.status = status
        existing.score = score
        existing.reason = reason
        existing.error_type = error_type
        existing.error_message = error_message
        existing.eval_latency_s = eval_latency_s
        existing.evaluated_at = evaluated_at
