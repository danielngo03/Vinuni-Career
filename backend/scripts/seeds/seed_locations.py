"""Seed provinces and wards from JSON into the database.

Run from the backend/ directory:

    python scripts/seeds/seed_locations.py           # insert / skip existing
    python scripts/seeds/seed_locations.py --reset   # truncate then insert

Use --reset only on a fresh / empty database (e.g. first production deploy).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import get_settings
from app.shared.location_models import Province, Ward
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

SEEDS_DIR = Path(__file__).parent


async def seed_into_session(
    session: AsyncSession,
    *,
    reset: bool = False,
) -> tuple[int, int, int, int]:
    """Insert/update provinces and wards using an existing transaction."""

    provinces_data = json.loads((SEEDS_DIR / "provinces.json").read_text(encoding="utf-8"))
    wards_data = json.loads((SEEDS_DIR / "wards.json").read_text(encoding="utf-8"))

    if reset:
        await session.execute(delete(Ward))
        await session.execute(delete(Province))
        print("[seed] Cleared provinces and wards.")

    # ── Provinces ────────────────────────────────────────────────
    existing_provinces = {
        row[0] for row in (await session.execute(select(Province.code))).all()
    }

    new_provinces = [
        Province(
            code=p["code"],
            name=p["name"],
            full_name=p["fullName"],
            slug=p["slug"],
            type=p["type"],
            is_central=p.get("isCentral", False),
        )
        for p in provinces_data
        if p["code"] not in existing_provinces
    ]
    session.add_all(new_provinces)
    await session.flush()

    # ── Wards ────────────────────────────────────────────────────
    existing_wards = {
        row[0] for row in (await session.execute(select(Ward.code))).all()
    }

    batch: list[Ward] = []
    BATCH_SIZE = 500
    inserted_wards = 0

    for w in wards_data:
        if w["code"] in existing_wards:
            continue
        batch.append(Ward(
            code=w["code"],
            name=w["name"],
            full_name=w["fullName"],
            slug=w["slug"],
            type=w["type"],
            province_code=w["provinceCode"],
        ))
        if len(batch) >= BATCH_SIZE:
            session.add_all(batch)
            await session.flush()
            inserted_wards += len(batch)
            batch = []

    if batch:
        session.add_all(batch)
        await session.flush()
        inserted_wards += len(batch)

    return (
        len(new_provinces),
        len(provinces_data) - len(new_provinces),
        inserted_wards,
        len(wards_data) - inserted_wards,
    )


async def seed(reset: bool = False) -> None:
    cfg = get_settings()
    engine = create_async_engine(str(cfg.database_url), echo=False)

    async with AsyncSession(engine) as session:
        async with session.begin():
            new_provinces, skipped_p, inserted_wards, skipped_w = (
                await seed_into_session(session, reset=reset)
            )

    await engine.dispose()

    print(
        f"[seed] Provinces: {new_provinces} inserted"
        + (f", {skipped_p} already existed" if skipped_p else "")
    )
    print(
        f"[seed] Wards: {inserted_wards} inserted"
        + (f", {skipped_w} already existed" if skipped_w else "")
    )
    print("[seed] Done.")


if __name__ == "__main__":
    asyncio.run(seed(reset="--reset" in sys.argv))
