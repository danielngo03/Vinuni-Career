"""Alembic async migration environment.

The database URL is taken from application settings (``backend/.env``) and the
target metadata aggregates every ORM model via ``app.core.metadata``.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from app.core.config import get_settings
from app.core.metadata import import_all_models, target_metadata
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import_all_models()

settings = get_settings()
DB_URL = settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    import sqlalchemy as sa
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # Revision IDs use descriptive names longer than Alembic's default 32-char cap
        version_num_type=sa.String(128),
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = DB_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
