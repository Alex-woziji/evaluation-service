from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvalLog

logger = logging.getLogger(__name__)


async def upsert_eval_log(
    session: AsyncSession,
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
) -> None:
    eval_id_str = str(eval_id)

    existing = await session.get(EvalLog, eval_id_str)
    if existing is None:
        session.add(
            EvalLog(
                id=eval_id_str,
                metric_type=metric_type,
                status=status,
                score=score,
                scores_detail=scores_detail,
                reasoning=reasoning,
                error_type=error_type,
                error_message=error_message,
                retry_count=retry_count,
                eval_latency_ms=eval_latency_ms,
                evaluated_at=evaluated_at,
            )
        )
    else:
        existing.metric_type = metric_type
        existing.status = status
        existing.score = score
        existing.scores_detail = scores_detail
        existing.reasoning = reasoning
        existing.error_type = error_type
        existing.error_message = error_message
        existing.retry_count = retry_count
        existing.eval_latency_ms = eval_latency_ms
        existing.evaluated_at = evaluated_at

    await session.commit()
