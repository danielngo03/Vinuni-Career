"""Reset the local/dev database schema.

Usage:
    cd backend
    uv run python scripts/reset_local_db.py --yes

This is intentionally destructive and guarded to local/dev/test environments.
It drops and recreates the PostgreSQL ``public`` schema; run Alembic + seed
scripts immediately afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings

_ALLOWED_ENVS = {"local", "dev", "development", "test", "testing"}


async def reset_schema() -> None:
    settings = get_settings()
    env = settings.app_env.strip().lower()
    if env not in _ALLOWED_ENVS:
        raise RuntimeError(
            f"Refusing to reset database when APP_ENV={settings.app_env!r}."
        )
    if not settings.database_url.startswith("postgresql"):
        raise RuntimeError("reset_local_db only supports PostgreSQL DATABASE_URL.")

    engine = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset local PostgreSQL schema.")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset.")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Pass --yes to confirm the destructive local DB reset.")
    asyncio.run(reset_schema())
    print("[reset] Dropped and recreated PostgreSQL public schema.")


if __name__ == "__main__":
    main()
