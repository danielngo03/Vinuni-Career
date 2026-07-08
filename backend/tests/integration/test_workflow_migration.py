from __future__ import annotations

from app.modules.organization.domain.catalog import is_catalog_permission


def test_workflow_permissions_registered() -> None:
    assert is_catalog_permission("workflow", "create")
    assert is_catalog_permission("workflow", "activate")
    assert not is_catalog_permission("workflow", "delete")
