"""Seed the industry taxonomy into the database.

Run from the backend/ directory:

    # Insert / update (idempotent — safe to re-run)
    python scripts/seeds/seed_industries.py

    # Reset all industries then re-insert
    python scripts/seeds/seed_industries.py --reset

When to use --reset:
    Use only on a fresh / empty database (e.g. first production deploy).
    Do NOT use --reset on a running production DB that already has company /
    job records referencing industry rows — it will violate foreign-key
    constraints (or orphan the references if FKs are deferred).
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

# Allow running as a plain script from the backend/ root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import get_settings
from app.modules.opportunities.domain.industry_models import Industry
from scripts.seeds.industry_taxonomy import INDUSTRY_TREE
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


async def _upsert_node(
    session: AsyncSession,
    node: dict,
    parent_id: uuid.UUID | None,
    level: int,
) -> None:
    slug = node["slug"]
    result = await session.execute(select(Industry).where(Industry.slug == slug))
    existing = result.scalar_one_or_none()

    if existing is None:
        row = Industry(
            id=uuid.uuid4(),
            slug=slug,
            name_vi=node["name_vi"],
            name_en=node["name_en"],
            level=level,
            parent_id=parent_id,
            sort_order=node.get("sort_order", 0),
            is_active=True,
        )
        session.add(row)
        await session.flush()
        industry_id = row.id
    else:
        existing.name_vi = node["name_vi"]
        existing.name_en = node["name_en"]
        existing.sort_order = node.get("sort_order", 0)
        await session.flush()
        industry_id = existing.id

    for child in node.get("children", []):
        await _upsert_node(session, child, industry_id, level + 1)


async def seed_into_session(session: AsyncSession, *, reset: bool = False) -> int:
    """Insert/update taxonomy using an existing transaction."""

    if reset:
        # Delete leaf → branch → root to satisfy FK RESTRICT
        for lvl in (2, 1, 0):
            await session.execute(delete(Industry).where(Industry.level == lvl))
        print("[seed] Cleared all industry rows.")

    for root in INDUSTRY_TREE:
        await _upsert_node(session, root, None, 0)

    def count(nodes: list) -> int:
        return sum(1 + count(n.get("children", [])) for n in nodes)

    return count(INDUSTRY_TREE)


async def seed(reset: bool = False) -> None:
    cfg = get_settings()
    engine = create_async_engine(str(cfg.database_url), echo=False)

    async with AsyncSession(engine) as session:
        async with session.begin():
            total = await seed_into_session(session, reset=reset)

    await engine.dispose()

    print(f"[seed] Done — {len(INDUSTRY_TREE)} root sectors, {total} total nodes seeded.")


if __name__ == "__main__":
    asyncio.run(seed(reset="--reset" in sys.argv))
