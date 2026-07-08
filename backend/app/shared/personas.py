"""Canonical auth-persona string constants (shared kernel).

``Principal.persona`` is a plain string assigned at login. These constants are
the SINGLE source of truth for those string values so lower layers (``app/ai``)
and the ``ai_assistant`` module can reference them without re-declaring literals
or reaching across a module boundary into ``app.modules.auth`` (a layering
violation). ``app.modules.auth.domain.personas`` keeps its own copy for the auth
bootstrap map, but every value here MUST stay byte-identical to it.

Kept as plain strings (not an enum) so a new persona can be added without a
migration; RBAC enforcement lives in the service/permission layer, not here.
"""

from __future__ import annotations

from typing import Final

STUDENT: Final = "student"
ALUMNI: Final = "alumni"
PARTNER_MEMBER: Final = "partner_member"
UNIVERSITY_STAFF: Final = "university_staff"
GUEST: Final = "guest"

# Personas whose AI budget/tooling is scoped to a shared partner ORG pool rather
# than an individual USER scope. A frozenset so callers can do fast membership
# tests (``principal.persona in ORG_PERSONAS``) without re-declaring the set.
ORG_PERSONAS: Final = frozenset({PARTNER_MEMBER})
