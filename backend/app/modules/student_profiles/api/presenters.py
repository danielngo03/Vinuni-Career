"""ORM -> friendly, leak-safe response shapes for the student-profile API.

Two audiences:

- :func:`owner_profile` — the full profile the owning student sees, including the
  ``profile_completion`` metric and raw contact fields.
- :func:`public_profile` — the privacy-gated projection a partner / VinUni-community
  viewer sees. Contact fields appear ONLY when the relevant per-field gate allows
  it for the caller's context; the completion metric is never exposed; hidden
  sections are omitted entirely (not nulled).

Every raw enum code is paired with a localized label (``.claude/rules/backend.md``).
"""

from __future__ import annotations

from app.core.config import get_settings
from app.modules.student_profiles.domain import vocab
from app.modules.student_profiles.domain.models import (
    StudentEducation,
    StudentExperience,
    StudentLink,
    StudentProfile,
    StudentSkill,
)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


# --------------------------------------------------------------------------- #
# Child items                                                                  #
# --------------------------------------------------------------------------- #


def education(e: StudentEducation, *, locale: str = "vi") -> dict:
    return {
        "id": str(e.id),
        "institution": e.institution,
        "degree": e.degree,
        "field_of_study": e.field_of_study,
        "start_date": _iso(e.start_date),
        "end_date": _iso(e.end_date),
        "is_current": e.is_current,
        "gpa": float(e.gpa) if e.gpa is not None else None,
        "description": e.description,
        "sort_order": e.sort_order,
        "version": e.version,
    }


def experience(x: StudentExperience, *, locale: str = "vi") -> dict:
    return {
        "id": str(x.id),
        "company_name": x.company_name,
        "title": x.title,
        "employment_type": x.employment_type,
        "employment_type_label": vocab.employment_label(x.employment_type, locale=locale),
        "location": x.location,
        "start_date": _iso(x.start_date),
        "end_date": _iso(x.end_date),
        "is_current": x.is_current,
        "description": x.description,
        "skills_used": list(x.skills_used or []),
        "sort_order": x.sort_order,
        "version": x.version,
    }


def skill(s: StudentSkill, *, locale: str = "vi") -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "category": s.category,
        "category_label": vocab.skill_category_label(s.category, locale=locale),
        "proficiency": s.proficiency,
        "sort_order": s.sort_order,
        "version": s.version,
    }


def link(link_row: StudentLink, *, locale: str = "vi") -> dict:
    return {
        "id": str(link_row.id),
        "label": link_row.label,
        "url": link_row.url,
        "sort_order": link_row.sort_order,
        "version": link_row.version,
    }


# --------------------------------------------------------------------------- #
# Profile (owner / public)                                                     #
# --------------------------------------------------------------------------- #


def _avatar_url(p: StudentProfile) -> str | None:
    if not getattr(p, "avatar_path", None):
        return None
    base = get_settings().app_url.rstrip("/")
    return f"{base}/api/v1/students/{p.id}/avatar?v={p.version}"


# Exported alias for use by other modules (talent pool service etc.)
avatar_url_for = _avatar_url


def _open_to_work_labels(types: list[str], *, locale: str) -> list[str]:
    out = []
    for t in types or []:
        label = vocab.open_to_work_label(t, locale=locale)
        if label:
            out.append(label)
    return out


def owner_profile(
    p: StudentProfile,
    *,
    user,
    educations: list[StudentEducation],
    experiences: list[StudentExperience],
    skills: list[StudentSkill],
    links: list[StudentLink],
    locale: str = "vi",
) -> dict:
    return {
        "id": str(p.id),
        "user_id": str(p.user_id),
        "display_name": (getattr(user, "full_name", None) or "") if user else "",
        "email": (getattr(user, "email", None) or "") if user else "",
        "avatar_url": _avatar_url(p),
        "headline": p.headline,
        "summary": p.summary,
        "phone": p.phone,
        "location_city": p.location_city,
        "location_country": p.location_country,
        "major": p.major,
        "degree_level": p.degree_level,
        "degree_level_label": vocab.degree_label(p.degree_level, locale=locale),
        "graduation_year": p.graduation_year,
        "profile_visibility": p.profile_visibility,
        "profile_visibility_label": vocab.visibility_label(
            p.profile_visibility, locale=locale
        ),
        "show_email": p.show_email,
        "show_email_label": vocab.contact_label(p.show_email, locale=locale),
        "show_phone": p.show_phone,
        "show_phone_label": vocab.contact_label(p.show_phone, locale=locale),
        "is_open_to_work": p.is_open_to_work,
        "open_to_work_types": list(p.open_to_work_types or []),
        "open_to_work_type_labels": _open_to_work_labels(
            list(p.open_to_work_types or []), locale=locale
        ),
        "profile_completion": p.profile_completion,
        "education": [education(e, locale=locale) for e in educations],
        "experience": [experience(x, locale=locale) for x in experiences],
        "skills": [skill(s, locale=locale) for s in skills],
        "links": [link(link_row, locale=locale) for link_row in links],
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
        "version": p.version,
    }


def _public_education(e: StudentEducation, *, locale: str) -> dict:
    # Public projection keeps school identity but drops the private GPA + notes.
    return {
        "id": str(e.id),
        "institution": e.institution,
        "degree": e.degree,
        "field_of_study": e.field_of_study,
        "start_date": _iso(e.start_date),
        "end_date": _iso(e.end_date),
        "is_current": e.is_current,
    }


def _public_experience(x: StudentExperience, *, locale: str) -> dict:
    return {
        "id": str(x.id),
        "company_name": x.company_name,
        "title": x.title,
        "employment_type": x.employment_type,
        "employment_type_label": vocab.employment_label(x.employment_type, locale=locale),
        "location": x.location,
        "start_date": _iso(x.start_date),
        "end_date": _iso(x.end_date),
        "is_current": x.is_current,
        "skills_used": list(x.skills_used or []),
    }


def public_profile(
    p: StudentProfile,
    *,
    user,
    educations: list[StudentEducation],
    experiences: list[StudentExperience],
    skills: list[StudentSkill],
    links: list[StudentLink],
    expose_email: bool,
    expose_phone: bool,
    locale: str = "vi",
) -> dict:
    """Privacy-gated projection. ``profile_completion`` is intentionally absent.

    ``expose_email`` / ``expose_phone`` are decided by the visibility service from
    the per-field gate + caller context; this presenter only renders what it is
    told it may render and never leaks raw contact otherwise.
    """

    body: dict = {
        "id": str(p.id),
        "user_id": str(p.user_id),
        "display_name": (getattr(user, "full_name", None) or "") if user else "",
        "avatar_url": _avatar_url(p),
        "headline": p.headline,
        "summary": p.summary,
        "location_city": p.location_city,
        "location_country": p.location_country,
        "major": p.major,
        "degree_level": p.degree_level,
        "degree_level_label": vocab.degree_label(p.degree_level, locale=locale),
        "graduation_year": p.graduation_year,
        "is_open_to_work": p.is_open_to_work,
        "open_to_work_types": list(p.open_to_work_types or []),
        "open_to_work_type_labels": _open_to_work_labels(
            list(p.open_to_work_types or []), locale=locale
        ),
        "education": [_public_education(e, locale=locale) for e in educations],
        "experience": [_public_experience(x, locale=locale) for x in experiences],
        "skills": [skill(s, locale=locale) for s in skills],
        "links": [link(link_row, locale=locale) for link_row in links],
        "profile_visibility": p.profile_visibility,
    }
    if expose_email and user is not None:
        body["email"] = getattr(user, "email", None) or ""
    if expose_phone:
        body["phone"] = p.phone
    return body
