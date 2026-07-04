from __future__ import annotations

from app.modules.organization.domain.catalog import is_catalog_permission


def test_view_provider_identity_permission_registered() -> None:
    assert is_catalog_permission("ai_settings", "view_provider_identity")
    assert is_catalog_permission("ai_settings", "read")
    assert is_catalog_permission("ai_settings", "manage")
