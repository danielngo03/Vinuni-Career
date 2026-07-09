"""Shared helpers for recruitment (apply-flow) tests."""

from __future__ import annotations

import uuid

from app.modules.opportunities.application import job_service, moderation_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth_utils import CTX
from tests.documents_utils import make_ready_cv


def job_payload(title: str = "Backend Intern", **over) -> dict:
    base = {
        "title": title,
        "description": "We are hiring a backend intern to build APIs.",
        "employment_type": "internship",
        "location_type": "onsite",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["python"],
        "preferred_skills": [],
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "visibility": "public",
    }
    base.update(over)
    return base


async def publish_job(
    session: AsyncSession, *, partner_principal, uni_principal, title="Live Job", **over
) -> uuid.UUID:
    created = await job_service.create_job(
        session, principal=partner_principal, payload=job_payload(title, **over), ctx=CTX
    )
    job_id = uuid.UUID(created["id"])
    await job_service.submit_job(session, principal=partner_principal, job_id=job_id, ctx=CTX)
    await moderation_service.approve_job(session, principal=uni_principal, job_id=job_id, ctx=CTX)
    return job_id


async def make_builder_cv(session: AsyncSession, *, student) -> dict:
    """Create a builder CV, finalize it into the library, and return the cv_selection.

    A CV must be committed to the library (``status='ready'``) before it can be
    submitted with an application (design spec 2026-07-05), so this helper runs the
    real finalize path and returns the CURRENT head version id (finalize adds a new
    immutable version).
    """

    detail = await make_ready_cv(session, student=student, title="My CV")
    return {
        "type": "builder_cv",
        "cv_profile_id": detail["id"],
        "cv_version_id": detail["current_version_id"],
        "uploaded_document_id": None,
    }


def apply_payload(*, job_id: uuid.UUID, cv_selection: dict, **over) -> dict:
    base = {
        "job_id": job_id,
        "cv_selection": cv_selection,
        "cover_letter": "I am excited to apply.",
        "screening_answers": {},
        "is_anonymous": False,
        "idempotency_key": uuid.uuid4().hex,
    }
    base.update(over)
    return base
