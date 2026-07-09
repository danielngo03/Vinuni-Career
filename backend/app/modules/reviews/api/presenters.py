"""Review response presenters — friendly labels, anonymity + PII-safe (ADR-0013).

The public presenter NEVER emits ``reviewer_id`` and emits the author name only
when the review is non-anonymous; an anonymous review shows a neutral masked
label. Raw status/eligibility codes are mapped to labels via ``..domain.labels``.
"""

from __future__ import annotations

from app.modules.reviews.domain import labels
from app.modules.reviews.domain.models import CompanyReview, ReviewRating

_ANON_LABEL = {"vi": "Ứng viên ẩn danh", "en": "Anonymous candidate"}


def _ratings(rating: ReviewRating) -> dict:
    return {
        "overall": rating.overall,
        "work_life_balance": rating.work_life_balance,
        "culture_values": rating.culture_values,
        "compensation": rating.compensation,
        "career_growth": rating.career_growth,
        "interview_experience": rating.interview_experience,
    }


def _core(
    review: CompanyReview,
    rating: ReviewRating,
    *,
    locale: str,
    my_vote: bool | None = None,
) -> dict:
    return {
        "id": str(review.id),
        "title": review.title,
        "body": review.body,
        "pros": review.pros,
        "cons": review.cons,
        "ratings": _ratings(rating),
        "trust_label": labels.trust_label(review.eligibility_type, locale=locale),
        "is_anonymous": review.is_anonymous,
        "helpful_count": review.helpful_count,
        "my_vote": my_vote,
        "partner_response": review.partner_response,
        "partner_response_at": (
            review.partner_response_at.isoformat() if review.partner_response_at else None
        ),
        "published_at": review.published_at.isoformat() if review.published_at else None,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


def review_public(
    review: CompanyReview,
    rating: ReviewRating,
    *,
    author_name: str | None,
    locale: str = "vi",
    my_vote: bool | None = None,
) -> dict:
    """Guest/public shape — no reviewer_id; author masked when anonymous."""

    data = _core(review, rating, locale=locale, my_vote=my_vote)
    data["author_name"] = (
        _ANON_LABEL.get(locale, _ANON_LABEL["en"])
        if review.is_anonymous
        else (author_name or "VinUni")
    )
    return data


def review_owner(review: CompanyReview, rating: ReviewRating, *, locale: str = "vi") -> dict:
    """Author's own view — includes status + version for edit/optimistic lock."""

    data = _core(review, rating, locale=locale)
    data.update(
        {
            "status": review.status,
            "status_label": labels.status_label(review.status, locale=locale),
            "version": review.version,
        }
    )
    return data


def review_moderation(
    review: CompanyReview,
    rating: ReviewRating,
    *,
    author_name: str | None,
    locale: str = "vi",
) -> dict:
    """University moderation shape — author identity always visible (accountability)."""

    data = _core(review, rating, locale=locale)
    data.update(
        {
            "status": review.status,
            "status_label": labels.status_label(review.status, locale=locale),
            "version": review.version,
            "report_count": review.report_count,
            "author_name": author_name or "VinUni",
            "org_id": str(review.org_id),
        }
    )
    return data
