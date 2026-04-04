from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LLMMetadata

logger = logging.getLogger(__name__)


async def insert_llm_metadata(
    session: AsyncSession,
    evaluation_result_id: UUID,
    judge_model: str,
    attempt_number: int,
    prompt_system: Optional[str] = None,
    prompt_user: Optional[str] = None,
    raw_response: Optional[Dict[str, Any]] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    llm_latency_s: Optional[float] = None,
) -> None:
    log = LLMMetadata(
        evaluation_result_id=str(evaluation_result_id),
        judge_model=judge_model,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        raw_response=raw_response,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        llm_latency_s=llm_latency_s,
        attempt_number=attempt_number,
    )
    session.add(log)
    await session.commit()
