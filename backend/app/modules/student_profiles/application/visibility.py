"""Privacy / partner-visibility decision logic (``docs/SECURITY_PRIVACY.md`` §8).

Decides whether a non-owner caller may see a profile at all, and which contact
fields they may see. The rules are intentionally non-enumerable: a profile the
caller may not see is indistinguishable from a missing one (``404``).

Contact exposure tiers (per-field ``show_email`` / ``show_phone``):

- ``public``  -> exposed in any allowed view (including this passive read).
- ``invited`` -> exposed ONLY in an accepted application / reveal context, which is
  owned by the ``recruitment`` module; never in the passive read here.
- ``hidden``  -> never exposed to anyone but the owner.

This module deliberately does NOT read recruitment state; the application-context
exposure decision is passed in (``reveal_accepted``) by the caller that already
owns that handshake, so this slice never bypasses the recruitment reveal flow.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.student_profiles.application import _shared
from app.modules.student_profiles.domain import vocab
from app.modules.student_profiles.domain.models import StudentProfile
from app.shared.permissions import Principal


@dataclass(slots=True)
class ViewDecision:
    """Outcome of a visibility check for a non-owner viewer."""

    visible: bool
    expose_email: bool = False
    expose_phone: bool = False


def _staff_or_admin(principal: Principal) -> bool:
    return principal.is_superadmin or principal.persona == "university_staff"


def passive_view_decision(principal: Principal, profile: StudentProfile) -> ViewDecision:
    """Decision for the passive ``GET /students/{id}/profile`` read (no app context)."""

    if not principal.is_authenticated:
        return ViewDecision(visible=False)

    # University staff / superadmin: governance read of the full profile.
    if _staff_or_admin(principal):
        return ViewDecision(visible=True, expose_email=True, expose_phone=True)

    visibility = profile.profile_visibility
    if visibility == vocab.VISIBILITY_PRIVATE:
        return ViewDecision(visible=False)
    if visibility == vocab.VISIBILITY_VINUNI_ONLY and (
        principal.persona not in _shared.VINUNI_PERSONAS
    ):
        return ViewDecision(visible=False)

    # Public projection: only ``public`` per-field contact gates are exposed.
    return ViewDecision(
        visible=True,
        expose_email=(profile.show_email == vocab.CONTACT_PUBLIC),
        expose_phone=(profile.show_phone == vocab.CONTACT_PUBLIC),
    )


def application_context_decision(
    principal: Principal, profile: StudentProfile, *, reveal_accepted: bool
) -> ViewDecision:
    """Decision for a partner viewing within an application context.

    The caller (recruitment) has already established that this partner has a
    legitimate application relationship and whether the anonymous-reveal handshake
    was accepted. In that context ``invited`` contacts become visible once reveal
    is accepted; ``hidden`` contacts remain hidden always.
    """

    if not principal.is_authenticated:
        return ViewDecision(visible=False)

    def _expose(gate: str) -> bool:
        if gate == vocab.CONTACT_PUBLIC:
            return True
        if gate == vocab.CONTACT_INVITED:
            return reveal_accepted
        return False  # hidden

    return ViewDecision(
        visible=True,
        expose_email=_expose(profile.show_email),
        expose_phone=_expose(profile.show_phone),
    )
