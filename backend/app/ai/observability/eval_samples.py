"""1% online sampling to ai_eval_samples for async human review (AI_PRODUCT_SPEC §10.2).

Samples 1 in every 100 AI completions (configurable via AI_EVAL_SAMPLE_RATE env).
Sampled rows contain ONLY metadata — no prompt text, no completion content, no PII.
Human reviewers see task_type, chars buckets, model_alias, success flag, and can
add a quality score + notes in the review_notes column.
"""

from __future__ import annotations

import logging
import os
import random
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import Boolean, DateTime, ForeignKey, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.observability.usage import _db_bucket
from app.shared.models import Base

logger = logging.getLogger("ai.eval_samples")

_DEFAULT_SAMPLE_RATE = 0.01  # 1%


def _get_sample_rate() -> float:
    try:
        return float(os.environ.get("AI_EVAL_SAMPLE_RATE", _DEFAULT_SAMPLE_RATE))
    except (ValueError, TypeError):
        return _DEFAULT_SAMPLE_RATE


class AiEvalSample(Base):
    """Metadata-only sample row for async human quality review."""

    __tablename__ = "ai_eval_samples"

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    model_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_chars_bucket: Mapped[str] = mapped_column(String(8), nullable=False)
    completion_chars_bucket: Mapped[str] = mapped_column(String(8), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    quality_score: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


async def maybe_sample_async(
    db: AsyncSession,
    *,
    task_type: str,
    alias: str,
    success: bool,
    prompt_chars: int = 0,
    completion_chars: int = 0,
    user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
) -> None:
    """Probabilistically write a sample row (1% by default). Never raises."""
    if random.random() > _get_sample_rate():
        return
    try:
        row = AiEvalSample(
            task_type=task_type,
            model_alias=alias,
            prompt_chars_bucket=_db_bucket(prompt_chars),
            completion_chars_bucket=_db_bucket(completion_chars),
            user_id=user_id,
            session_id=session_id,
            success=success,
        )
        db.add(row)
        await db.flush([row])
    except Exception as exc:  # noqa: BLE001
        logger.warning("ai_eval_sample_write_failed", extra={"error": str(exc)})
