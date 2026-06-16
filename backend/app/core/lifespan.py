from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.infra.database.session import create_db_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Local/dev convenience. Production should run Alembic migrations explicitly.
    create_db_schema()
    yield
