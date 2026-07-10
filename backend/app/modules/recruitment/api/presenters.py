"""ORM -> friendly response shapes for applications.

Two audiences:

- :func:`applicant_application` — what the owning student sees (full own data).
- :func:`partner_application` — what a partner reviewing the job sees.

Identity model (owner decision 2026-07-10): an application ALWAYS exposes the
applicant's real identity (``user_id``, ``full_name``, ``avatar_url``, ``email``)
to any partner member who passes the CV / candidate RBAC gate. The former
anonymous-apply + identity-reveal handshake was removed; there is no masking and
no ``UV-xxxx`` handle. WHO may open the CV is still gated by
``candidate_identity:view_cv`` / ``download_cv`` and every sensitive access is
audited; the watermark on partner CV downloads is retained.

Every enum column is paired with a localized label; raw codes are never the only
signal and internal fields (rejection notes) are never leaked to the student.
"""

from __future__ import annotations

from app.modules.recruitment.domain import interview as interview_domain
from app.modules.recruitment.domain import lifecycle, scorecard
from app.modules.recruitment.domain import offer as offer_domain
from app.modules.recruitment.domain.models import (
    Application,
    Interview,
    Offer,
    Scorecard,
)
from app.modules.recruitment.infrastructure.meeting_link_crypto import (
    decrypt_meeting_link,
)
from app.modules.recruitment.infrastructure.offer_salary_crypto import decrypt_salary


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def applicant_block(
    app: Application,
    *,
    user,
    avatar_url: str | None = None,
    headline: str | None = None,
) -> dict:
    """The applicant's real identity as a partner sees it (never masked).

    ``user`` is a contact-like object carrying ``full_name`` / ``email`` (loaded
    by the service through the users facade); ``avatar_url`` is the safe serve
    pointer (never a raw storage key). ``headline`` is an optional pre-composed
    short descriptor ("grad-year · major", derived from the CV snapshot) for the
    candidate row/drawer secondary line — ``None`` when nothing is derivable (the
    UI falls back to email). The block is always fully identified — the partner has
    already passed the CV / candidate RBAC gate to reach it.
    """

    return {
        "user_id": str(app.applicant_id),
        "full_name": (getattr(user, "full_name", None) or "") if user else "",
        "avatar_url": avatar_url,
        "email": (getattr(user, "email", None) or "") if user else "",
        "headline": headline,
    }


def applicant_application(
    app: Application,
    *,
    job_title: str | None = None,
    company_name: str | None = None,
    timeline_events: list[dict] | None = None,
    next_action: str | None = None,
    messages_pointer: dict | None = None,
    locale: str = "vi",
) -> dict:
    return {
        "id": str(app.id),
        "job_id": str(app.job_id),
        "job_title": job_title,
        "company_name": company_name,
        "status": app.status,
        "status_label": lifecycle.status_label(app.status, locale=locale),
        "cover_letter": app.cover_letter,
        "screening_answers": dict(app.screening_answers or {}),
        "snapshot_id": str(app.snapshot_id) if app.snapshot_id else None,
        "applied_at": _iso(app.applied_at),
        "last_status_at": _iso(app.last_status_at),
        "created_at": _iso(app.created_at),
        "updated_at": _iso(app.updated_at),
        "version": app.version,
        # Real, server-computed timeline (docs/DATA_MODEL.md §32) — replaces the
        # frontend's prior client-side guess derived from ``status`` alone. Each
        # entry is ``{event_type, label, occurred_at}`` ONLY — never partner-
        # internal ``metadata`` (rejection reason, target stage), regardless of
        # event type.
        "timeline": timeline_events if timeline_events is not None else [],
        # Short machine-readable "what happens next" key for the student.
        "next_action": next_action,
        # Server-computed — the frontend must stop guessing this from ``status``.
        "can_withdraw": app.status in lifecycle.WITHDRAWABLE_STATES,
        # ``{thread_id, unread_count}`` when a real application-bound message
        # thread exists for this student; ``null`` otherwise (never fabricated).
        "messages_pointer": messages_pointer,
    }


def partner_application(
    app: Application,
    *,
    applicant: dict,
    cv: dict | None = None,
    fit: dict | None = None,
    assignee: dict | None = None,
    stage: dict | None = None,
    screening: list[dict] | None = None,
    locale: str = "vi",
) -> dict:
    """One application as a partner sees it — always fully identified.

    ``applicant`` is the real identity block (:func:`applicant_block`). ``cv`` =
    ``{snapshot_id, filename, view_url, download_url, has_watermark:false}`` points
    at the STUDENT'S ORIGINAL file (owner decision 2026-07-10; never a watermarked
    derivative), permission-gated on ``candidate_identity:view_cv`` and DETAIL-only
    (``None`` on the flat list). ``fit`` is supplied on BOTH surfaces: the LIST
    carries the batched ``{score, band}`` (match ring); DETAIL carries the richer
    ``{score, band, reasons}``. ``fit`` is ``None`` when the CV-JD fit is not
    computable.
    """

    return {
        "id": str(app.id),
        "job_id": str(app.job_id),
        "status": app.status,
        "status_label": lifecycle.status_label(app.status, locale=locale),
        "applicant": applicant,
        "screening_answers": dict(app.screening_answers or {}),
        # DETAIL-only: each stored answer paired with its job screening-question
        # prompt (``[{question_id, question, answer}]``) so the drawer renders
        # "Question: … / Answer: …" instead of "Answer N". ``question`` is ``None``
        # when the job defines no matching prompt. ``None`` on the flat LIST.
        "screening": screening,
        "cover_letter": app.cover_letter,
        "snapshot_id": str(app.snapshot_id) if app.snapshot_id else None,
        # DETAIL-only: inline view + download URLs for the student's ORIGINAL CV
        # file (no watermark), permission-gated. ``None`` on the flat LIST.
        "cv": cv,
        # User-safe CV-JD fit. LIST: batched ``{score, band}`` (match ring). DETAIL:
        # ``{score, band, reasons}``. ``None`` when the fit is not computable.
        "fit": fit,
        # Decision metadata is partner/owner-only (the student view never carries
        # the coded reason or the partner's internal note). ``rejection_reason`` is
        # a stable machine code for partner-side filtering; it stays org-internal.
        "rejection_reason": app.rejection_reason,
        "rejection_note": app.rejection_note,
        # Candidate owner for multi-person teams: ``{membership_id, user_id,
        # display_name}`` of the assigned recruiter, or ``None`` when unassigned.
        # This is PARTNER staff (not the candidate).
        "assignee": assignee,
        # Current pipeline stage ``{stage_id, stage_name}`` (from the ACTIVE
        # ``candidate_stages`` row), or ``None`` for a pre-pipeline (still
        # ``submitted``) application. Lets the flat LIST show pipeline position
        # without opening the per-candidate detail (whose ``pipeline`` block
        # carries the full ladder).
        "stage": stage,
        "last_status_at": _iso(app.last_status_at),
        "applied_at": _iso(app.applied_at),
    }


def partner_board_card(
    app: Application,
    *,
    applicant: dict,
    stage_id: str | None,
    position: int | None,
    entered_at,
    rollback_count: int,
    evaluation: dict | None = None,
    assignee: dict | None = None,
    locale: str = "vi",
) -> dict:
    """A lean kanban CARD for the partner pipeline board.

    The card carries the applicant's real identity block; it never carries CV
    text, the cover letter, screening answers, or scores — a kanban glance is
    minimal by construction.
    """

    return {
        "application_id": str(app.id),
        "applicant": applicant,
        "status": app.status,
        "status_label": lifecycle.status_label(app.status, locale=locale),
        "stage_id": stage_id,
        "position": position,
        "entered_at": _iso(entered_at),
        "rollback_count": rollback_count,
        # Partner-only scorecard glance for the card's CURRENT stage (None when the
        # card is pre-pipeline). NEVER carries any student identity.
        "evaluation": evaluation,
        # Candidate owner for multi-person teams: ``{membership_id, user_id,
        # display_name}`` of the assigned recruiter, or ``None`` when unassigned.
        "assignee": assignee,
        "applied_at": _iso(app.applied_at),
        "last_status_at": _iso(app.last_status_at),
    }


# --------------------------------------------------------------------------- #
# Scorecards (ADR-0005) — PARTNER-INTERNAL; never in any student projection     #
# --------------------------------------------------------------------------- #


def _recommendation_label(code: str | None, *, locale: str) -> str | None:
    if not code:
        return None
    labels = scorecard.RECOMMENDATION_LABELS.get(code)
    if labels is None:
        return None
    return labels.get(locale, labels["vi"])


def _criterion_label(key: str, *, locale: str) -> str:
    labels = scorecard.CRITERION_LABELS.get(key)
    if labels is None:
        return key
    return labels.get(locale, labels["vi"])


def scorecard_detail(
    sc: Scorecard,
    *,
    scores: dict[str, int],
    is_mine: bool,
    locale: str = "vi",
) -> dict:
    """One scorecard as a partner sees it (anchoring/RBAC applied by the service).

    ``reviewer_id`` is a partner-org MEMBER id (never the student); the endpoint is
    partner-internal, so reviewer identity is visible only to same-org members. No
    student-identity field exists on a scorecard (ADR-0005 §4).
    """

    overall = sc.overall_score
    return {
        "id": str(sc.id),
        "stage_id": str(sc.stage_id),
        "reviewer_id": str(sc.submitted_by_user_id),
        "is_mine": is_mine,
        "recommendation": sc.recommendation,
        "recommendation_label": _recommendation_label(sc.recommendation, locale=locale),
        "overall_score": float(overall) if overall is not None else None,
        "scores": [
            {
                "criterion_key": key,
                "label": _criterion_label(key, locale=locale),
                "score": scores.get(key),
            }
            for key in scores
        ],
        "comment": sc.comment,
        "status": sc.status,
        "version": sc.version,
        "submitted_at": _iso(sc.submitted_at),
        "updated_at": _iso(sc.updated_at),
    }


def scorecard_criteria(*, locale: str = "vi") -> list[dict]:
    """The fixed V1 criteria set (labels) for the submit form."""

    return [
        {"criterion_key": c["key"], "label": _criterion_label(c["key"], locale=locale)}
        for c in scorecard.DEFAULT_CRITERIA
    ]


# --------------------------------------------------------------------------- #
# Interviews (ADR-0006) — meeting_link is ATTENDEE-ONLY                          #
# --------------------------------------------------------------------------- #


def _mode_label(mode: str, *, locale: str) -> str:
    labels = interview_domain.MODE_LABELS.get(mode)
    if labels is None:
        return mode
    return labels.get(locale, labels["vi"])


def interview_view(
    iv: Interview,
    *,
    assignees: list[dict],
    evaluation: dict | None,
    viewer_is_attendee: bool,
    locale: str = "vi",
) -> dict:
    """The partner interview view (partner-internal).

    ``meeting_link`` is decrypted ONLY for an attendee viewer (the candidate or an
    assigned interviewer) — it is absent for every non-attendee partner member and
    never appears on the board glance. ``assignees`` is a list of
    ``{user_id, name}`` (partner-org members; never the student). ``evaluation`` is
    the partner-only gate summary for the interview's stage.
    """

    meeting_link = decrypt_meeting_link(iv.meeting_link) if viewer_is_attendee else None
    return {
        "id": str(iv.id),
        "application_id": str(iv.application_id),
        "stage_id": str(iv.stage_id),
        "title": iv.title,
        "mode": iv.mode,
        "mode_label": _mode_label(iv.mode, locale=locale),
        "scheduled_at": _iso(iv.scheduled_at),
        "duration_minutes": iv.duration_minutes,
        "location": iv.location,
        # Attendee-only; non-attendee partner members never receive the link.
        "meeting_link": meeting_link,
        "status": iv.status,
        "notes": iv.notes,
        "assignees": assignees,
        "evaluation": evaluation,
        "version": iv.version,
        "created_at": _iso(iv.created_at),
        "updated_at": _iso(iv.updated_at),
    }


def student_interview_card(iv: Interview, *, locale: str = "vi") -> dict:
    """The candidate's OWN upcoming-interview card (identity-safe).

    The student is an attendee, so date/time/mode + their location-or-link is shown.
    NEVER carries assignee identities, scorecards, the gate, or any other internal
    field (ADR-0006 §7 / PRD §7.6 "Không hiện: assignee").
    """

    if iv.mode == interview_domain.MODE_ONLINE:
        location_or_link = decrypt_meeting_link(iv.meeting_link)
    elif iv.mode == interview_domain.MODE_ONSITE:
        location_or_link = iv.location
    else:  # phone
        location_or_link = None
    return {
        "id": str(iv.id),
        "scheduled_at": _iso(iv.scheduled_at),
        "mode": iv.mode,
        "mode_label": _mode_label(iv.mode, locale=locale),
        "duration_minutes": iv.duration_minutes,
        "location_or_link": location_or_link,
        "status": iv.status,
    }


def interview_board_block(iv: Interview, *, assignee_count: int) -> dict:
    """The partner-only board/detail interview glance (NO meeting_link).

    Surfaced on the current-stage pipeline block so a partner sees a scheduled
    interview at a glance. ``meeting_link`` is deliberately absent (attendee-only).
    """

    return {
        "id": str(iv.id),
        "mode": iv.mode,
        "scheduled_at": _iso(iv.scheduled_at),
        "status": iv.status,
        "assignee_count": assignee_count,
    }


# --------------------------------------------------------------------------- #
# Offers (ADR-0007) — salary is recruiter + owning-student only                 #
# --------------------------------------------------------------------------- #


def _offer_status_label(code: str, *, locale: str) -> str:
    return offer_domain.status_label(code, locale=locale)


def _decrypt_amount(offer: Offer) -> int | None:
    """Decrypt the at-rest salary ciphertext to an int (recruiter/student only)."""

    plain = decrypt_salary(offer.salary_amount)
    if plain is None or plain == "":
        return None
    try:
        return int(plain)
    except (TypeError, ValueError):
        return None


def _comp_summary(offer: Offer, *, locale: str) -> str | None:
    """A short human comp string for a recruiter/owning-student surface.

    Returns ``None`` when no salary was set (a comp summary is shown only when the
    figure exists). NEVER built for a notification/board/event surface.
    """

    amount = _decrypt_amount(offer)
    if amount is None:
        return None
    period = offer_domain.period_label(offer.salary_period, locale=locale)
    return f"{amount:,} {offer.salary_currency}/{period}"


def _offer_comp_fields(offer: Offer, *, locale: str) -> dict:
    """The decrypted comp block shared by the partner + owning-student views."""

    return {
        "salary_amount": _decrypt_amount(offer),
        "salary_currency": offer.salary_currency,
        "salary_period": offer.salary_period,
        "comp_summary": _comp_summary(offer, locale=locale),
    }


def partner_offer(offer: Offer, *, locale: str = "vi") -> dict:
    """The partner offer view (partner-internal): FULL comp + the approval trail.

    Salary is decrypted for the partner (recruiter surface, DATA_MODEL §17). The
    approval actor/timestamps and the candidate's ``decline_reason`` are partner-
    internal and surfaced here (never on a student surface).
    """

    body = {
        "id": str(offer.id),
        "application_id": str(offer.application_id),
        "stage_id": str(offer.stage_id),
        "status": offer.status,
        "status_label": _offer_status_label(offer.status, locale=locale),
        "position_title": offer.position_title,
        "department": offer.department,
        "start_date": _iso(offer.start_date),
        "benefits_summary": offer.benefits_summary,
        "terms_notes": offer.terms_notes,
        "expiry_date": _iso(offer.expiry_date),
        "created_by": str(offer.created_by),
        "approved_by": str(offer.approved_by) if offer.approved_by else None,
        "approved_at": _iso(offer.approved_at),
        "sent_at": _iso(offer.sent_at),
        "student_response_at": _iso(offer.student_response_at),
        "decline_reason": offer.decline_reason,
        "version": offer.version,
        "created_at": _iso(offer.created_at),
        "updated_at": _iso(offer.updated_at),
    }
    body.update(_offer_comp_fields(offer, locale=locale))
    return body


def student_offer(offer: Offer, *, locale: str = "vi") -> dict:
    """The owning student's OWN offer view — full comp; partner internals stripped.

    The student is the owner, so their comp is decrypted for them (DATA_MODEL §17).
    Partner internals — ``approved_by``/``approved_at``, ``created_by``,
    ``decline_reason`` — are NEVER surfaced. Only ``sent``+terminal offers are ever
    exposed to the student (drafts/pending/approved are partner-internal).
    """

    body = {
        "id": str(offer.id),
        "application_id": str(offer.application_id),
        "status": offer.status,
        "status_label": _offer_status_label(offer.status, locale=locale),
        "position_title": offer.position_title,
        "department": offer.department,
        "start_date": _iso(offer.start_date),
        "benefits_summary": offer.benefits_summary,
        "terms_notes": offer.terms_notes,
        "expiry_date": _iso(offer.expiry_date),
        "sent_at": _iso(offer.sent_at),
        "student_response_at": _iso(offer.student_response_at),
        "version": offer.version,
    }
    body.update(_offer_comp_fields(offer, locale=locale))
    return body


def offer_board_block(offer: Offer, *, locale: str = "vi") -> dict:
    """The partner-only board/detail offer glance — NO salary (open detail to see).

    Surfaced on the current-stage pipeline block so a partner sees an offer's status
    + deadline at a glance. Comp is deliberately ABSENT (recruiter detail only).
    """

    return {
        "id": str(offer.id),
        "status": offer.status,
        "status_label": _offer_status_label(offer.status, locale=locale),
        "expiry_date": _iso(offer.expiry_date),
        "sent_at": _iso(offer.sent_at),
    }


def student_offer_card(offer: Offer, *, locale: str = "vi") -> dict:
    """The candidate's OWN offer summary card for the application timeline.

    Identity-safe to the owner: position, their own comp summary, start date,
    deadline. NEVER partner internals (``approved_by``, ``decline_reason``) and never
    surfaced for a draft/pending/approved offer (those are partner-internal).
    """

    return {
        "id": str(offer.id),
        "status": offer.status,
        "status_label": _offer_status_label(offer.status, locale=locale),
        "position_title": offer.position_title,
        "department": offer.department,
        "start_date": _iso(offer.start_date),
        "expiry_date": _iso(offer.expiry_date),
        "comp_summary": _comp_summary(offer, locale=locale),
    }
