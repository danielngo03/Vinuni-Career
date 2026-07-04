"""Province and Ward ORM models — read-only reference data.

Two-level Vietnamese administrative hierarchy (post-2025 reform):
  Province / City  (34 tỉnh/thành phố)
    └── Ward / Commune  (3 320 xã/phường)

Seeded from static JSON. Never mutated by users or admins at runtime.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.models import Base


class Province(Base):
    """Tỉnh / Thành phố trực thuộc trung ương."""

    __tablename__ = "provinces"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)

    # Short display name — e.g. "Hà Nội"
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Full official name — e.g. "Thành phố Hà Nội"
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)

    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)

    # "city" | "province"
    type: Mapped[str] = mapped_column(String(20), nullable=False)

    # True for the 5 centrally-administered municipalities
    is_central: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    wards: Mapped[list[Ward]] = relationship(
        "Ward",
        back_populates="province",
        foreign_keys="Ward.province_code",
        order_by="Ward.name",
    )


class Ward(Base):
    """Xã / Phường / Thị trấn."""

    __tablename__ = "wards"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)

    # Short name without prefix — e.g. "Rạch Giá"
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Name with administrative prefix — e.g. "Phường Rạch Giá"
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)

    slug: Mapped[str] = mapped_column(String(130), nullable=False)

    # "ward" | "commune"
    type: Mapped[str] = mapped_column(String(20), nullable=False)

    province_code: Mapped[str] = mapped_column(
        ForeignKey("provinces.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    province: Mapped[Province] = relationship(
        "Province",
        back_populates="wards",
        foreign_keys=[province_code],
    )
