"""Central RBAC gate for AI-assistant tool invocation.

Single source of truth for "may this principal invoke this tool". It is used in
two places so every path fails closed:

1. **Offer-time filtering** — ``available_specs`` decides which tools are even
   described to the model (``native_loop``/``chat_service``), so the model is
   never told about a tool the caller can't use.
2. **Execution-time re-check** — ``dispatch_tool`` calls :func:`is_authorized`
   again before running ANY handler. A tool the model manages to name anyway
   (a hallucinated name, a replayed confirmation, the legacy plan loop) is
   refused here even if its handler forgets a service-layer check.

The two-layer design matters because tool handlers historically enforced their
own RBAC unevenly: read-only, persona-only tools relied on not being offered.
Centralizing the gate means a persona/grant mismatch can never execute,
regardless of which loop dispatched it.

Interpretation of ``ToolSpec.required_permissions`` (ALL must pass):
- ``"authenticated"``       → the principal has a user id.
- ``"role:<persona>"``      → persona-family match (student / partner / university).
- ``"<resource>:<action>"`` → ``permission_checker.can`` (real grant + tenant scope).
- anything else             → treated as unknown; require at least authentication.
"""

from __future__ import annotations

from app.modules.ai_assistant.application.tools.specs import (
    PARTNER_USER,
    STUDENT,
    UNIVERSITY_STAFF,
    ToolSpec,
)
from app.shared.permissions import Principal, permission_checker


def persona_token(principal: Principal) -> str | None:
    """Map a real login persona to the ``ToolSpec.persona`` vocabulary token.

    Returns ``None`` for an unrecognised persona (guest/system) — then the
    persona filter is a no-op and only the permission grants gate the tool
    (which still requires ``"authenticated"`` for every real tool).
    """

    persona = principal.persona or ""
    if persona == "student":
        return STUDENT
    if persona.startswith("partner"):
        return PARTNER_USER
    if persona.startswith("university"):
        return UNIVERSITY_STAFF
    return None


def persona_matches_role(principal: Principal, want: str) -> bool:
    persona = principal.persona or ""
    if want == "student":
        return persona == "student"
    if want in ("partner_user", "partner", "partner_member"):
        return persona.startswith("partner")
    if want in ("university_staff", "university"):
        return persona.startswith("university")
    return persona == want


def satisfies_permissions(principal: Principal, spec: ToolSpec) -> bool:
    """True iff the principal satisfies every ``required_permissions`` entry."""

    for req in spec.required_permissions:
        if req == "authenticated":
            if not principal.is_authenticated:
                return False
        elif req.startswith("role:"):
            if not persona_matches_role(principal, req.split(":", 1)[1]):
                return False
        elif ":" in req:
            resource, action = req.split(":", 1)
            if not permission_checker.can(
                principal, resource, action, resource_org_id=principal.org_id
            ):
                return False
        else:  # unknown token — require at least authentication
            if not principal.is_authenticated:
                return False
    return True


def is_authorized(principal: Principal, spec: ToolSpec) -> bool:
    """Full gate: persona-scoped AND grant-authorized (fail-closed).

    This is the single predicate both the offer-time filter and the
    execution-time re-check use, so they can never disagree.
    """

    token = persona_token(principal)
    if token is not None and token not in spec.persona:
        return False
    return satisfies_permissions(principal, spec)


# Back-compat alias: ``native_loop`` historically exposed this name.
def authorize_tool(principal: Principal, spec: ToolSpec) -> bool:
    """Grant-only check (no persona-scope filter). Kept for the offer-time
    filter, which applies the persona filter separately. Prefer
    :func:`is_authorized` for a complete gate."""

    return satisfies_permissions(principal, spec)


def available_specs(principal: Principal) -> list[ToolSpec]:
    """Tools this principal may use: persona-scoped AND grant-authorized."""

    from app.modules.ai_assistant.application.tools.specs import TOOL_SPECS

    return [spec for spec in TOOL_SPECS.values() if is_authorized(principal, spec)]
