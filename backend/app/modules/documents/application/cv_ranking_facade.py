"""Read facade: the caller's active CVs as deterministic :class:`job_fit.CvInput`s.

The ``discovery`` ranker scores a candidate job set against the student's CV
library to produce the ``cv_fit`` reason code + ``recommended_cv_id`` per job. It
must reuse the SAME deterministic scorer the CV-to-job fit feature uses
(``app.ai.cv.job_fit``) — but build the CV inputs **once** for a page of jobs
rather than reloading the library per job, and WITHOUT any AI call (ranking does
not depend on AI, spec §9). This facade owner-checks the caller and returns the
prepared ``CvInput`` list; the ranker then calls ``job_fit.evaluate`` per job.

No provider/model/token/embedding internals are ever produced here — the score
that results is a product fit score, not a model confidence.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import job_fit
from app.modules.documents.application import _shared, job_fit_service
from app.shared.permissions import Principal, permission_checker


async def build_cv_inputs(session: AsyncSession, *, principal: Principal) -> list[job_fit.CvInput]:
    """The caller's active CVs prepared for deterministic fit scoring.

    Owner-only (``cv:read``). Empty list when the student has no active CV — the
    ranker then omits the ``cv_fit`` signal entirely (honest: no CV, no CV reason).
    """

    permission_checker.require(principal, _shared.RESOURCE, "read")
    assert principal.user_id is not None

    now = datetime.now(tz=UTC)
    cvs = await job_fit_service._load_active_cvs(session, user_id=principal.user_id)
    return [await job_fit_service._build_cv_input(session, cv=cv, now=now) for cv in cvs]
