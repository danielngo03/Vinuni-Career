"""Internal opaque-token facade for cross-module invitation/verification flows.

``organization`` (team invitations) mints/hashes the same opaque secret token
shape ``auth`` uses for refresh/verification tokens. It goes through this seam
instead of importing ``auth.infrastructure.tokens`` directly, so the module
boundary holds (`docs/ARCHITECTURE.md`: communicate through interfaces/read
models). No auth session/JWT internals are exposed here — just the two pure
token-shape helpers.
"""

from __future__ import annotations

from app.modules.auth.infrastructure.tokens import generate_token, hash_token

__all__ = ["generate_token", "hash_token"]
