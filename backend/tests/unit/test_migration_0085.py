"""Migration 0085 (university control plane P1) — well-formed + symmetric.

The real Postgres up/down/up is exercised via ``alembic`` in CI. Here we assert
the migration module is well-formed (revision chain, callable upgrade/downgrade),
that every ``upgrade`` create has a matching ``downgrade`` drop (symmetry), and
that the new schema objects register on the ORM metadata (SQLite create-all).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.core.metadata import import_all_models, target_metadata
from sqlalchemy import create_engine

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION = _VERSIONS / "0085_ai_capacity_requests_and_usage_department.py"


def _load():
    spec = importlib.util.spec_from_file_location("migration_0085", _MIGRATION)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0085_well_formed() -> None:
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert mod.revision == "0085_ai_capacity_requests_and_usage_department"
    assert mod.down_revision == "0084_ai_energy_accounts_and_usage_org"


def test_migration_0085_upgrade_downgrade_symmetric() -> None:
    source = _MIGRATION.read_text(encoding="utf-8")
    # Every additive op in upgrade() has an inverse in downgrade().
    assert source.count("op.create_table(") == source.count("op.drop_table(")
    assert source.count("op.add_column(") == source.count("op.drop_column(")
    assert source.count("op.create_index(") == source.count("op.drop_index(")
    # The specific objects.
    assert 'op.create_table(\n        "ai_capacity_requests"' in source
    assert 'op.drop_table("ai_capacity_requests")' in source
    assert 'op.add_column(\n        "ai_billable_usage"' in source
    assert 'op.drop_column("ai_billable_usage", "department_id")' in source


def test_new_tables_and_columns_registered_on_metadata() -> None:
    import_all_models()
    tables = target_metadata.tables
    assert "ai_capacity_requests" in tables
    assert "department_id" in tables["ai_billable_usage"].columns


def test_metadata_create_and_drop_round_trip() -> None:
    import_all_models()
    engine = create_engine("sqlite://")
    target_metadata.create_all(engine)
    assert "ai_capacity_requests" in set(target_metadata.tables.keys())
    target_metadata.drop_all(engine)
    engine.dispose()
