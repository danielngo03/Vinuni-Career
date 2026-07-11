"""Public reference data: Vietnamese provinces for location pickers and job map.

GET /locations/provinces  — list all 34 provinces (lightweight: code, name, slug, type)
GET /locations/provinces/{code}/wards  — list wards under a province (for fine-grained
    address pickers)

These are read-only seed data; no auth required.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.shared.location_models import Province, Ward

router = APIRouter(prefix="/locations", tags=["locations"])


def _province_dto(p: Province) -> dict:
    return {
        "code": p.code,
        "name": p.name,
        "full_name": p.full_name,
        "slug": p.slug,
        "type": p.type,
        "is_central": p.is_central,
    }


def _ward_dto(w: Ward) -> dict:
    return {
        "code": w.code,
        "name": w.name,
        "full_name": w.full_name,
        "slug": w.slug,
        "type": w.type,
    }


@router.get("/provinces", summary="List all Vietnamese provinces/cities")
async def list_provinces(
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    rows = (await session.execute(select(Province).order_by(Province.name))).scalars().all()
    return {"items": [_province_dto(p) for p in rows]}


@router.get("/provinces/{code}/wards", summary="List wards in a province")
async def list_province_wards(
    code: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    rows = (
        (await session.execute(select(Ward).where(Ward.province_code == code).order_by(Ward.name)))
        .scalars()
        .all()
    )
    return {"items": [_ward_dto(w) for w in rows]}
