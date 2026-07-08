"""Migration sanity for 0084 (mock interview).

Mirrors ``tests/unit/test_migration.py``: assert the alembic revision is
well-formed (has ``upgrade``/``downgrade`` and the right revision chain) and that
both ORM tables register on ``target_metadata`` and survive a SQLite
create/drop round-trip (fast proxy for the real Postgres up/down).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.core.metadata import import_all_models, target_metadata
from sqlalchemy import create_engine

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_0084 = _VERSIONS / "0084_mock_interview.py"

_TABLES = {"mock_interview_sessions", "mock_interview_turns"}


def _load_migration(path=_MIGRATION_0084, name="mock_interview_migration"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mock_interview_migration_well_formed() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert mod.revision == "0084_mock_interview"
    assert mod.down_revision == "0083_ai_billable_usage"


def test_mock_interview_tables_registered_on_metadata() -> None:
    import_all_models()
    names = set(target_metadata.tables.keys())
    assert _TABLES <= names


def test_mock_interview_metadata_round_trip() -> None:
    import_all_models()
    engine = create_engine("sqlite://")
    target_metadata.create_all(engine)
    assert _TABLES <= set(target_metadata.tables.keys())
    target_metadata.drop_all(engine)
    engine.dispose()


def test_mock_interview_turns_fk_and_indexes_present() -> None:
    import_all_models()
    sessions = target_metadata.tables["mock_interview_sessions"]
    turns = target_metadata.tables["mock_interview_turns"]

    # Owner + job foreign keys exist on the session table.
    fk_targets = {fk.referred_table.name for fk in sessions.foreign_key_constraints}
    assert {"users", "jobs"} <= fk_targets

    # Turns cascade from their session.
    turn_fk_targets = {fk.referred_table.name for fk in turns.foreign_key_constraints}
    assert "mock_interview_sessions" in turn_fk_targets

    index_names = {ix.name for ix in sessions.indexes}
    assert "ix_mock_interview_sessions_user_created" in index_names
