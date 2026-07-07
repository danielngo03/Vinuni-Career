"""Core student-profile use cases for the identity-only profile: read own,
update own, and the privacy-gated partner/community read.

Owner decision (2026-07-06): the profile is identity-only. It has no career
content and no completion metric — all career content lives in the student's CVs
(``documents`` module). The only career signal here is ``is_open_to_work``.

RBAC is enforced here (not in routers):

- The owning student holds ``profile:*``; ``get_my_profile`` lazily materializes
  an empty profile on first read so the student always has something to edit.
- ``update_my_profile`` validates vocabulary and enforces optimistic ``version``.
- ``get_profile_for_viewer`` serves the ``/students/{id}/profile`` read: the owner
  and university staff see the full profile; everyone else gets a privacy-gated
  public projection or ``404`` (non-enumerable) per :mod:`visibility`.

Every write is audited inside the caller's transaction.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.student_profiles.api import presenters
from app.modules.student_profiles.application import _shared, visibility
from app.modules.student_profiles.application.errors import (
    InvalidProfileFieldError,
    ProfileVersionConflictError,
)
from app.modules.student_profiles.domain import vocab
from app.modules.student_profiles.domain.models import StudentProfile
from app.modules.users.application import user_service
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


# --------------------------------------------------------------------------- #
# Response assembly                                                            #
# --------------------------------------------------------------------------- #


async def _owner_response(
    session: AsyncSession, *, profile: StudentProfile, locale: str
) -> dict:
    user = await user_service.get_by_id(session, profile.user_id)
    return presenters.owner_profile(profile, user=user, locale=locale)


async def _public_response(
    session: AsyncSession,
    *,
    profile: StudentProfile,
    decision: visibility.ViewDecision,
    locale: str,
) -> dict:
    user = await user_service.get_by_id(session, profile.user_id)
    return presenters.public_profile(
        profile,
        user=user,
        expose_email=decision.expose_email,
        expose_phone=decision.expose_phone,
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Own profile: read + update                                                   #
# --------------------------------------------------------------------------- #


async def get_my_profile(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    permission_checker.require(principal, _RESOURCE, "read")
    profile = await _shared.load_owned_profile(session, principal=principal)
    # Lazy-create commits so a first GET persists the empty profile shell.
    await session.commit()
    await session.refresh(profile)
    return await _owner_response(session, profile=profile, locale=locale)


_TEXT_FIELDS = {"phone", "location_city", "location_country"}


async def update_my_profile(
    session: AsyncSession,
    *,
    principal: Principal,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    profile = await _shared.load_owned_profile(session, principal=principal, lock=True)

    expected = payload.get("expected_version")
    if expected is not None and expected != profile.version:
        raise ProfileVersionConflictError(current_version=profile.version)

    _validate_enums(payload)

    changed: list[str] = []
    for field in _TEXT_FIELDS:
        if field in payload:
            setattr(profile, field, payload[field])
            changed.append(field)

    if "profile_visibility" in payload:
        profile.profile_visibility = payload["profile_visibility"]
        changed.append("profile_visibility")
    if "show_email" in payload:
        profile.show_email = payload["show_email"]
        changed.append("show_email")
    if "show_phone" in payload:
        profile.show_phone = payload["show_phone"]
        changed.append("show_phone")
    if "is_open_to_work" in payload:
        profile.is_open_to_work = bool(payload["is_open_to_work"])
        changed.append("is_open_to_work")

    if changed:
        profile.version += 1
    await session.flush()

    await write_audit(
        session,
        action="student_profile.updated",
        resource_type="student_profile",
        resource_id=profile.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"fields": sorted(changed)},
    )
    await session.commit()
    await session.refresh(profile)
    return await _owner_response(session, profile=profile, locale=locale)


def _validate_enums(payload: dict) -> None:
    if payload.get("profile_visibility") is not None and (
        payload["profile_visibility"] not in vocab.PROFILE_VISIBILITY
    ):
        raise InvalidProfileFieldError(field="profile_visibility")
    if payload.get("show_email") is not None and (
        payload["show_email"] not in vocab.CONTACT_VISIBILITY
    ):
        raise InvalidProfileFieldError(field="show_email")
    if payload.get("show_phone") is not None and (
        payload["show_phone"] not in vocab.CONTACT_VISIBILITY
    ):
        raise InvalidProfileFieldError(field="show_phone")


# --------------------------------------------------------------------------- #
# Partner / community read of another student's profile                        #
# --------------------------------------------------------------------------- #


async def get_profile_for_viewer(
    session: AsyncSession,
    *,
    principal: Principal,
    profile_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Privacy-gated read of ``/students/{id}/profile`` (``id`` = profile id)."""

    if not principal.is_authenticated:
        # Authentication is required to view any profile.
        from app.shared.exceptions import AuthRequiredError

        raise AuthRequiredError()

    profile = await _shared.load_profile_by_id(session, profile_id=profile_id)

    # Owner -> full own view.
    if profile.user_id == principal.user_id:
        return await _owner_response(session, profile=profile, locale=locale)

    decision = visibility.passive_view_decision(principal, profile)
    if not decision.visible:
        # Non-enumerable: a hidden profile looks exactly like a missing one.
        raise ResourceNotFoundError()

    # Staff/superadmin get the full governance view.
    if principal.is_superadmin or principal.persona == "university_staff":
        return await _owner_response(session, profile=profile, locale=locale)

    return await _public_response(
        session, profile=profile, decision=decision, locale=locale
    )


# --------------------------------------------------------------------------- #
# Interface seam: application-context read (called BY recruitment)             #
# --------------------------------------------------------------------------- #


async def get_profile_for_application_context(
    session: AsyncSession,
    *,
    viewer_principal: Principal,
    applicant_user_id: uuid.UUID,
    reveal_accepted: bool,
    locale: str = "vi",
) -> dict | None:
    """Identity projection for a partner reviewing an application.

    Exposed as a service interface for the ``recruitment`` module: recruitment owns
    the decision that this partner has a legitimate application relationship and
    whether the anonymous-reveal handshake was accepted, and passes
    ``reveal_accepted`` in. ``invited`` contacts become visible once revealed. This
    function never reads recruitment state, so it cannot bypass that flow.

    Returns ``None`` if the student has no profile yet.
    """

    profile = await _shared.load_profile_by_user(session, user_id=applicant_user_id)
    if profile is None:
        return None
    decision = visibility.application_context_decision(
        viewer_principal, profile, reveal_accepted=reveal_accepted
    )
    return await _public_response(
        session, profile=profile, decision=decision, locale=locale
    )
