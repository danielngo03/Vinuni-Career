"""Industry taxonomy API routes.

Public:
  GET  /api/v1/industries           — full tree (cached)
  GET  /api/v1/industries/{id}      — single node with children

Admin (governed by the ``taxonomy:manage`` catalog grant on a university-org
role, or platform superadmin — enforced in ``industry_taxonomy_service`` at the
service layer, NOT here):
  POST   /api/v1/admin/industries
  PATCH  /api/v1/admin/industries/{id}
  DELETE /api/v1/admin/industries/{id}   (soft-deactivate, not hard-delete)
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.modules.auth.api.deps import CurrentAuth, get_current_auth
from app.modules.opportunities.application import industry_taxonomy_service
from app.modules.opportunities.domain.industry_models import Industry

industries_router = APIRouter(prefix="/industries", tags=["industries"])
admin_industries_router = APIRouter(
    prefix="/admin/industries", tags=["admin-industries"]
)


# ── Schemas ────────────────────────────────────────────────────────────────


class IndustryLeafOut(BaseModel):
    id: uuid.UUID
    slug: str
    name_vi: str
    name_en: str
    level: int
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}


class IndustryBranchOut(IndustryLeafOut):
    children: list[IndustryLeafOut] = []


class IndustryRootOut(IndustryLeafOut):
    children: list[IndustryBranchOut] = []


class IndustryCreateRequest(BaseModel):
    name_vi: str = Field(..., min_length=1, max_length=150)
    name_en: str = Field(..., min_length=1, max_length=150)
    slug: str = Field(..., min_length=1, max_length=160, pattern=r"^[a-z0-9-]+$")
    parent_id: uuid.UUID | None = None
    sort_order: int = 0


class IndustryUpdateRequest(BaseModel):
    name_vi: str | None = Field(None, min_length=1, max_length=150)
    name_en: str | None = Field(None, min_length=1, max_length=150)
    sort_order: int | None = None
    is_active: bool | None = None


# ── Helpers ────────────────────────────────────────────────────────────────


async def _get_or_404(db: AsyncSession, industry_id: uuid.UUID) -> Industry:
    row = await db.get(Industry, industry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Industry not found.")
    return row


# ── Public routes ──────────────────────────────────────────────────────────


@industries_router.get("", response_model=list[IndustryRootOut], summary="Full industry tree")
async def list_industries(db: AsyncSession = Depends(get_db_session)) -> Any:
    """Return the full active industry tree (roots → branches → leaves).
    Suitable for populating dropdowns and faceted search filters.
    """
    result = await db.execute(
        select(Industry)
        .where(Industry.is_active.is_(True), Industry.level == 0)
        .order_by(Industry.sort_order)
    )
    roots = result.scalars().all()

    out: list[IndustryRootOut] = []
    for root in roots:
        # Eager-load children (2 levels)
        branches_result = await db.execute(
            select(Industry)
            .where(Industry.parent_id == root.id, Industry.is_active.is_(True))
            .order_by(Industry.sort_order)
        )
        branches = branches_result.scalars().all()
        branch_out: list[IndustryBranchOut] = []
        for branch in branches:
            leaves_result = await db.execute(
                select(Industry)
                .where(Industry.parent_id == branch.id, Industry.is_active.is_(True))
                .order_by(Industry.sort_order)
            )
            leaves = leaves_result.scalars().all()
            branch_out.append(
                IndustryBranchOut(
                    **branch.__dict__,
                    children=[IndustryLeafOut.model_validate(leaf) for leaf in leaves],
                )
            )
        out.append(IndustryRootOut(**root.__dict__, children=branch_out))
    return out


@industries_router.get(
    "/{industry_id}",
    response_model=IndustryBranchOut,
    summary="Single industry node with immediate children",
)
async def get_industry(
    industry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    row = await _get_or_404(db, industry_id)
    children_result = await db.execute(
        select(Industry)
        .where(Industry.parent_id == row.id, Industry.is_active.is_(True))
        .order_by(Industry.sort_order)
    )
    children = children_result.scalars().all()
    return IndustryBranchOut(
        **row.__dict__,
        children=[IndustryLeafOut.model_validate(c) for c in children],
    )


# ── Admin routes ───────────────────────────────────────────────────────────


@admin_industries_router.post(
    "",
    response_model=IndustryLeafOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new industry node (admin)",
)
async def create_industry(
    body: IndustryCreateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    return await industry_taxonomy_service.create_industry(
        db, principal=auth.principal, name_vi=body.name_vi, name_en=body.name_en,
        slug=body.slug, parent_id=body.parent_id, sort_order=body.sort_order,
        ctx=auth.ctx,
    )


@admin_industries_router.patch(
    "/{industry_id}",
    response_model=IndustryLeafOut,
    summary="Update industry node (admin)",
)
async def update_industry(
    industry_id: uuid.UUID,
    body: IndustryUpdateRequest,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    return await industry_taxonomy_service.update_industry(
        db, principal=auth.principal, industry_id=industry_id, name_vi=body.name_vi,
        name_en=body.name_en, sort_order=body.sort_order, is_active=body.is_active,
        ctx=auth.ctx,
    )


@admin_industries_router.delete(
    "/{industry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate an industry node (admin, soft-delete)",
)
async def deactivate_industry(
    industry_id: uuid.UUID,
    auth: CurrentAuth = Depends(get_current_auth),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    await industry_taxonomy_service.deactivate_industry(
        db, principal=auth.principal, industry_id=industry_id, ctx=auth.ctx
    )
