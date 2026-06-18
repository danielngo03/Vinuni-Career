from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.shared.config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_db_schema() -> None:
    # Import models before create_all so SQLAlchemy knows every table.
    from app.platform.database import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()


def ensure_schema_compatibility() -> None:
    inspector = inspect(engine)
    if "ai_usage_logs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("ai_usage_logs")}
    additions = {
        "provider": "VARCHAR(80)",
        "model": "VARCHAR(255)",
        "request_id": "VARCHAR(120)",
        "raw_usage": "JSON",
    }
    with engine.begin() as connection:
        for name, ddl_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE ai_usage_logs ADD COLUMN {name} {ddl_type}"))
