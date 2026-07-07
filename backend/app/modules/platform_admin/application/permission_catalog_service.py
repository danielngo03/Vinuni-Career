"""Platform Admin — Permission Catalog service (P5).

Exposes the static PERMISSION_CATALOG from the organization domain as a
sorted, serialisable list for the admin UI's permission matrix.

No DB access, no auth gate here; the router enforces superadmin.
"""

from __future__ import annotations

from typing import Any

from app.modules.organization.domain.catalog import PERMISSION_CATALOG


def permission_catalog() -> list[dict[str, Any]]:
    """Return the full permission catalog sorted by resource name.

    Shape: [{"resource": str, "actions": [str, ...]}, ...]
    Actions within each resource are also sorted for stable rendering.
    """
    return [
        {
            "resource": resource,
            "actions": sorted(actions),
        }
        for resource, actions in sorted(PERMISSION_CATALOG.items())
    ]
