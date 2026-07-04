"""Idempotent seeder for default notification templates.

Inserts the baseline ``account.*`` email templates (vi + en) that the auth
foundation relies on, so :func:`process_outbox` renders them instead of failing
with ``TEMPLATE_NOT_FOUND``. Safe to run repeatedly — existing templates for the
same ``(key, channel, locale)`` are left untouched.

Run from ``backend/``::

    uv run python -m scripts.seed_notification_templates

The API also runs this on startup (see ``app/bootstrap/lifespan.py``); the script
exists for explicit/CI seeding against a known database.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import dispose_engine, get_sessionmaker
from app.core.metadata import import_all_models
from app.modules.notifications.application.template_seed import ensure_default_templates


async def _main() -> None:
    import_all_models()
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        created = await ensure_default_templates(session)
        await session.commit()
    await dispose_engine()
    print(f"seed_notification_templates: created {created} template(s)")


if __name__ == "__main__":
    asyncio.run(_main())
