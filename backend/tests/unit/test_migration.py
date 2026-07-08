"""Baseline migration sanity: has upgrade + downgrade and a clean schema round-trip.

The real Postgres up/down/up is exercised via ``alembic`` in CI/verification. Here
we assert the migration module is well-formed and that the ORM metadata can be
created and dropped on SQLite (a fast schema round-trip proxy).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.core.metadata import import_all_models, target_metadata
from sqlalchemy import create_engine

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION = _VERSIONS / "0001_baseline.py"
_MIGRATION_0003 = _VERSIONS / "0003_organization_rbac.py"
_MIGRATION_0004 = _VERSIONS / "0004_opportunities.py"
_MIGRATION_0005 = _VERSIONS / "0005_documents.py"
_MIGRATION_0006 = _VERSIONS / "0006_recruitment.py"
_MIGRATION_0065 = _VERSIONS / "0065_cv_template_themes_governance.py"


def _load_migration(path=_MIGRATION, name="baseline_migration"):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_baseline_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert mod.revision == "0001_baseline"
    assert mod.down_revision is None


def test_org_rbac_migration_well_formed() -> None:
    mod = _load_migration(_MIGRATION_0003, "org_rbac_migration")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert mod.revision == "0003_organization_rbac"
    assert mod.down_revision == "0002_auth_identity_core"


def test_opportunities_migration_well_formed() -> None:
    mod = _load_migration(_MIGRATION_0004, "opportunities_migration")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert mod.revision == "0004_opportunities"
    assert mod.down_revision == "0003_organization_rbac"


def test_documents_migration_well_formed() -> None:
    mod = _load_migration(_MIGRATION_0005, "documents_migration")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert mod.revision == "0005_documents"
    assert mod.down_revision == "0004_opportunities"


def test_recruitment_migration_well_formed() -> None:
    mod = _load_migration(_MIGRATION_0006, "recruitment_migration")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert mod.revision == "0006_recruitment"
    assert mod.down_revision == "0005_documents"


def test_cv_template_themes_migration_well_formed() -> None:
    mod = _load_migration(_MIGRATION_0065, "cv_template_themes_migration")
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    assert mod.revision == "0065_cv_template_themes_governance"
    assert mod.down_revision == "0064_remove_cv_primary_flags"


def test_cv_template_versions_registered_on_metadata() -> None:
    import_all_models()
    names = set(target_metadata.tables.keys())
    assert "cv_template_versions" in names


def test_recruitment_tables_registered_on_metadata() -> None:
    import_all_models()
    names = set(target_metadata.tables.keys())
    assert {"applications", "application_reveal_requests"} <= names


def test_documents_tables_registered_on_metadata() -> None:
    import_all_models()
    names = set(target_metadata.tables.keys())
    assert {
        "cv_templates",
        "documents",
        "cv_parse_runs",
        "cv_profiles",
        "cv_sections",
        "cv_versions",
        "cv_exports",
        "signed_file_accesses",
        "application_cv_snapshots",
    } <= names


def test_org_tables_registered_on_metadata() -> None:
    import_all_models()
    names = set(target_metadata.tables.keys())
    assert {
        "organizations",
        "departments",
        "roles",
        "permissions",
        "memberships",
        "membership_roles",
        "membership_departments",
        "invitations",
        "partner_registration_requests",
    } <= names


def test_metadata_create_and_drop_round_trip() -> None:
    import_all_models()
    engine = create_engine("sqlite://")
    target_metadata.create_all(engine)
    table_names = set(target_metadata.tables.keys())
    assert {
        "outbox_events",
        "audit_logs",
        "notification_templates",
        "notification_outbox",
    } <= table_names
    target_metadata.drop_all(engine)
    engine.dispose()
