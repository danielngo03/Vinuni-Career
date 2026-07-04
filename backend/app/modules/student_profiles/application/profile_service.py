"""Core student-profile use cases: read own, update own, and the privacy-gated
partner/community read.

RBAC is enforced here (not in routers):

- The owning student holds ``profile:*``; ``get_my_profile`` lazily materializes
  an empty profile on first read so the student always has something to edit.
- ``update_my_profile`` validates vocabulary, enforces optimistic ``version``, and
  recomputes the completion cache.
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
from app.modules.student_profiles.application import _shared, loaders, visibility
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
    return presenters.owner_profile(
        profile,
        user=user,
        educations=await loaders.load_education(session, student_id=profile.id),
        experiences=await loaders.load_experience(session, student_id=profile.id),
        skills=await loaders.load_skills(session, student_id=profile.id),
        links=await loaders.load_links(session, student_id=profile.id),
        locale=locale,
    )


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
        educations=await loaders.load_education(session, student_id=profile.id),
        experiences=await loaders.load_experience(session, student_id=profile.id),
        skills=await loaders.load_skills(session, student_id=profile.id),
        links=await loaders.load_links(session, student_id=profile.id),
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
    await loaders.recompute_completion(session, profile=profile)
    await session.commit()
    await session.refresh(profile)
    return await _owner_response(session, profile=profile, locale=locale)


_TEXT_FIELDS = {"headline", "summary", "phone", "location_city", "location_country", "major"}


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

    if "degree_level" in payload:
        profile.degree_level = payload["degree_level"]
        changed.append("degree_level")
    if "graduation_year" in payload:
        profile.graduation_year = payload["graduation_year"]
        changed.append("graduation_year")
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
    if "open_to_work_types" in payload:
        profile.open_to_work_types = list(payload["open_to_work_types"] or [])
        changed.append("open_to_work_types")

    if changed:
        profile.version += 1
    await loaders.recompute_completion(session, profile=profile)
    await session.flush()

    await write_audit(
        session,
        action="student_profile.updated",
        resource_type="student_profile",
        resource_id=profile.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"fields": sorted(changed), "completion": profile.profile_completion},
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
    if payload.get("degree_level") is not None and (
        payload["degree_level"] not in vocab.DEGREE_LEVELS
    ):
        raise InvalidProfileFieldError(field="degree_level")
    types = payload.get("open_to_work_types")
    if types is not None:
        if not isinstance(types, list) or any(
            t not in vocab.OPEN_TO_WORK_TYPES for t in types
        ):
            raise InvalidProfileFieldError(field="open_to_work_types")


async def get_completion_for_user(
    session: AsyncSession, *, principal: Principal
) -> int:
    """Owner's cached profile-completion percentage (dashboard read model).

    Reads the persisted ``profile_completion`` cache without materializing an
    empty profile shell (unlike ``get_my_profile``) so a dashboard GET stays a
    pure read. Returns ``0`` when the student has no profile yet.
    """

    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None
    profile = await _shared.load_profile_by_user(session, user_id=principal.user_id)
    if profile is None:
        return 0
    return int(profile.profile_completion or 0)


async def get_completion_detail_for_user(
    session: AsyncSession, *, principal: Principal
) -> dict:
    """Per-section profile completion for the student dashboard onboarding card.

    Returns ``{"pct": int, "sections": [{key, done, weight, href}]}``.
    Runs lightweight count queries; the 7 sections mirror
    :mod:`completion.py` exactly so the scores are consistent with the cache.
    """
    from sqlalchemy import func
    from sqlalchemy import select as sa_select

    from app.modules.student_profiles.domain.completion import (
        SKILLS_TARGET,
        W_EDUCATION,
        W_EXPERIENCE,
        W_HEADLINE,
        W_LINKS,
        W_OPEN_TO_WORK,
        W_SKILLS,
        W_SUMMARY,
        CompletionInputs,
        compute,
    )
    from app.modules.student_profiles.domain.models import (
        StudentEducation,
        StudentExperience,
        StudentLink,
        StudentSkill,
    )

    permission_checker.require(principal, _RESOURCE, "read")
    assert principal.user_id is not None
    profile = await _shared.load_profile_by_user(session, user_id=principal.user_id)
    if profile is None:
        href = "/student/profile"
        empty: list[dict] = [
            {"key": "headline", "done": False, "weight": W_HEADLINE, "href": href},
            {"key": "summary", "done": False, "weight": W_SUMMARY, "href": href},
            {"key": "education", "done": False, "weight": W_EDUCATION, "href": href},
            {"key": "experience", "done": False, "weight": W_EXPERIENCE, "href": href},
            {"key": "skills", "done": False, "weight": W_SKILLS, "href": href},
            {"key": "links", "done": False, "weight": W_LINKS, "href": href},
            {"key": "open_to_work", "done": False, "weight": W_OPEN_TO_WORK, "href": href},
        ]
        return {"pct": 0, "sections": empty}

    async def _count(
        model: type[StudentEducation]
        | type[StudentExperience]
        | type[StudentSkill]
        | type[StudentLink],
    ) -> int:
        return (
            await session.execute(
                sa_select(func.count())
                .select_from(model)
                .where(model.student_id == profile.id, model.deleted_at.is_(None))
            )
        ).scalar_one()

    edu = await _count(StudentEducation)
    exp = await _count(StudentExperience)
    skills = await _count(StudentSkill)
    links = await _count(StudentLink)

    inputs = CompletionInputs(
        has_headline=bool(profile.headline and profile.headline.strip()),
        has_summary=bool(profile.summary and profile.summary.strip()),
        education_count=edu,
        experience_count=exp,
        skill_count=skills,
        link_count=links,
        open_to_work_configured=bool(
            profile.is_open_to_work and (profile.open_to_work_types or [])
        ),
    )
    pct = compute(inputs)
    href = "/student/profile"
    sections = [
        {"key": "headline", "done": inputs.has_headline, "weight": W_HEADLINE, "href": href},
        {"key": "summary", "done": inputs.has_summary, "weight": W_SUMMARY, "href": href},
        {
            "key": "education",
            "done": inputs.education_count >= 1,
            "weight": W_EDUCATION,
            "href": href,
        },
        {
            "key": "experience",
            "done": inputs.experience_count >= 1,
            "weight": W_EXPERIENCE,
            "href": href,
        },
        {
            "key": "skills",
            "done": inputs.skill_count >= SKILLS_TARGET,
            "weight": W_SKILLS,
            "href": href,
        },
        {"key": "links", "done": inputs.link_count >= 1, "weight": W_LINKS, "href": href},
        {
            "key": "open_to_work",
            "done": inputs.open_to_work_configured,
            "weight": W_OPEN_TO_WORK,
            "href": href,
        },
    ]
    return {"pct": pct, "sections": sections}


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
    """Richer projection for a partner reviewing an application.

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


# --------------------------------------------------------------------------- #
# AI skill suggestions                                                         #
# --------------------------------------------------------------------------- #

_CURATED_FALLBACK: list[str] = [
    "Python", "JavaScript", "SQL", "Excel", "Data Analysis",
    "Microsoft Office", "Research", "Communication", "Project Management",
    "Git", "Problem Solving", "Presentation", "Teamwork", "Critical Thinking",
]


async def get_ai_skill_suggestions(
    session: AsyncSession, *, principal: Principal
) -> dict:
    """Return AI-suggested skills the student might have but hasn't added yet."""
    permission_checker.require(principal, _RESOURCE, "read")
    profile = await _shared.load_owned_profile(session, principal=principal)

    existing_skills = await loaders.load_skills(session, student_id=profile.id)
    existing_names_lower = {(s.name or "").lower() for s in existing_skills}

    experiences = await loaders.load_experience(session, student_id=profile.id)
    exp_titles = [e.title for e in experiences if e.title]

    from app.ai.cv.llm import generate_json_note
    from app.ai.prompts.skill_suggest import v1 as prompt_mod

    try:
        user_msg = prompt_mod.build_user_message(
            major=profile.major or "",
            headline=profile.headline or "",
            experience_titles=exp_titles,
            existing_skills=[s.name for s in existing_skills if s.name],
        )
        result = await generate_json_note(
            task_type="skill_suggest",
            system_prompt=prompt_mod.STATIC_SYSTEM_PROMPT,
            user_content=user_msg,
            temperature=0.4,
            max_tokens=256,
        )
        suggestions = [
            s for s in (result.get("suggestions") or [])
            if isinstance(s, str) and s.lower() not in existing_names_lower
        ][:8]
        is_fallback = False
    except Exception:
        suggestions = [
            s for s in _CURATED_FALLBACK
            if s.lower() not in existing_names_lower
        ][:8]
        is_fallback = True

    return {
        "suggestions": suggestions,
        "is_fallback": is_fallback,
        "prompt_version": prompt_mod.PROMPT_VERSION,
    }


async def get_ai_summary_draft(
    session: AsyncSession, *, principal: Principal
) -> dict:
    """Return an AI-drafted profile summary paragraph."""
    permission_checker.require(principal, _RESOURCE, "read")
    profile = await _shared.load_owned_profile(session, principal=principal)

    skills = await loaders.load_skills(session, student_id=profile.id)
    experiences = await loaders.load_experience(session, student_id=profile.id)

    assert principal.user_id is not None  # guaranteed by permission_checker.require above
    user_obj = await user_service.get_by_id(session, principal.user_id)
    name = (getattr(user_obj, "full_name", None) or "").strip()

    from app.ai.cv.llm import generate_note
    from app.ai.prompts.profile_summary import v1 as prompt_mod

    _FALLBACK = (
        "I am a {degree} student majoring in {major} at VinUni. "
        "I am passionate about applying my skills to real-world challenges "
        "and eager to contribute to a dynamic team."
    )

    try:
        user_msg = prompt_mod.build_user_message(
            name=name,
            major=profile.major or "",
            degree_level=profile.degree_level or "",
            headline=profile.headline or "",
            experience_titles=[e.title for e in experiences if e.title],
            skills=[s.name for s in skills if s.name],
        )
        draft = await generate_note(
            task_type="profile_summary",
            system_prompt=prompt_mod.STATIC_SYSTEM_PROMPT,
            user_content=user_msg,
            temperature=0.5,
            max_tokens=256,
        )
        is_fallback = False
    except Exception:
        draft = _FALLBACK.format(
            degree=profile.degree_level or "university",
            major=profile.major or "my field",
        )
        is_fallback = True

    return {
        "draft": draft.strip(),
        "is_fallback": is_fallback,
        "prompt_version": prompt_mod.PROMPT_VERSION,
    }


async def get_ai_career_snapshot(
    session: AsyncSession, *, principal: Principal
) -> dict:
    """Generate a 2-3 sentence AI career snapshot for the student's job search status.

    Reads application counts from the recruitment module and profile data to
    produce a personalized, supportive summary. Falls back to a static message
    if AI is unavailable. Never exposes provider/model/token internals.
    """

    from app.ai.cv.llm import generate_note
    from app.ai.prompts.career_snapshot import v1 as prompt_mod
    from app.modules.recruitment.application.dashboard_read import (
        count_student_applications,
        list_upcoming_student_interviews,
    )

    permission_checker.require(principal, _RESOURCE, "read")
    profile = await _shared.load_owned_profile(session, principal=principal)
    assert principal.user_id is not None

    app_counts = await count_student_applications(session, user_id=principal.user_id)
    upcoming = await list_upcoming_student_interviews(session, user_id=principal.user_id, limit=5)
    interviews_upcoming = len(upcoming)

    offers_pending = 0
    most_recent_status: str | None = None

    is_fallback = False
    try:
        user_msg = prompt_mod.build_user_message(
            total_applications=app_counts["total"],
            active_applications=app_counts["active"],
            interviews_upcoming=interviews_upcoming,
            offers_pending=offers_pending,
            most_recent_status=most_recent_status,
            open_to_work=bool(profile.is_open_to_work),
            headline=profile.headline,
        )
        snapshot = await generate_note(
            task_type="career_snapshot",
            system_prompt=prompt_mod.STATIC_SYSTEM_PROMPT,
            user_content=user_msg,
            temperature=0.4,
            max_tokens=128,
        )
    except Exception:
        total = app_counts["total"]
        if total == 0:
            snapshot = (
                "You haven't applied to any positions yet. "
                "Start exploring jobs that match your skills and interests — "
                "your first application is the most important step."
            )
        else:
            active = app_counts["active"]
            snapshot = (
                f"You have sent {total} application{'' if total == 1 else 's'} "
                f"with {active} still active in the process. "
                "Keep engaging with recruiters and preparing for interviews."
            )
        is_fallback = True

    return {
        "snapshot": snapshot.strip(),
        "is_fallback": is_fallback,
        "prompt_version": prompt_mod.PROMPT_VERSION,
    }
