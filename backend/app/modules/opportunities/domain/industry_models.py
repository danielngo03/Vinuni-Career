"""Industry taxonomy ORM model — self-referential, 3-level hierarchy.

Level 0 (root): major sector, e.g. "Công nghệ thông tin"
Level 1 (branch): sub-domain, e.g. "Khoa học dữ liệu"
Level 2 (leaf): specific discipline, e.g. "Phân tích dữ liệu"

Only university admins may write; the list is publicly readable.
Bilingual: name_vi + name_en are both required.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import Base, TimestampMixin


class Industry(Base, TimestampMixin):
    """Hierarchical industry / career-field taxonomy node."""

    __tablename__ = "industries"
    __table_args__ = (UniqueConstraint("slug", name="uq_industries_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4, primary_key=True)

    # Bilingual display names
    name_vi: Mapped[str] = mapped_column(String(150), nullable=False)
    name_en: Mapped[str] = mapped_column(String(150), nullable=False)

    # URL-safe key derived from English name (unique across all levels)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)

    # 0 = root sector / 1 = branch / 2 = leaf specialisation
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Self-referential parent; NULL for root nodes
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("industries.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    parent: Mapped[Industry | None] = relationship(
        "Industry",
        back_populates="children",
        remote_side="Industry.id",
        foreign_keys=[parent_id],
    )
    children: Mapped[list[Industry]] = relationship(
        "Industry",
        back_populates="parent",
        foreign_keys=[parent_id],
        order_by="Industry.sort_order",
        cascade="all, delete-orphan",
    )
