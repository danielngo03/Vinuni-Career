"""Auth dependencies for the AI ops admin surface.

``require_superadmin`` is now the canonical function from
``app.modules.auth.api.deps``.  It is re-exported here so that existing imports
of ``app.modules.ai_ops.api.deps.require_superadmin`` continue to work without
modification.
"""

from __future__ import annotations

# Re-export from the canonical shared location.
from app.modules.auth.api.deps import require_superadmin as require_superadmin

__all__ = ["require_superadmin"]
