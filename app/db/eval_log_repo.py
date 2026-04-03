from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
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
    stmt = (
        insert(EvalLog)
        .values(
            id=eval_id,
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
        .on_conflict_do_update(
            index_elements=["id"],
            set_={
                "status": status,
                "score": score,
                "scores_detail": scores_detail,
                "reasoning": reasoning,
                "error_type": error_type,
                "error_message": error_message,
                "retry_count": retry_count,
                "eval_latency_ms": eval_latency_ms,
                "evaluated_at": evaluated_at,
            },
        )
    )
    await session.execute(stmt)
    await session.commit()
