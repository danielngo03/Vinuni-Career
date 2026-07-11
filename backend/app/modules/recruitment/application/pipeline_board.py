"""Partner pipeline kanban board read model (``GET /jobs/{job_id}/pipeline``).

A read-only facade (no writes, no audit) that loads the WHOLE kanban board for one
of the caller-org's jobs in a small, bounded number of queries — never a
per-application fetch loop (ADR-0004 kanban data note + the ``backend.md`` "no
heavy live joins / no N+1" rule).

Query budget (independent of candidate count):

1. load the job (org-scope gate, ``404`` cross-org — same authz as
   ``apply_service.list_job_applications``);
2. ensure + read the org's default template stages (the kanban COLUMNS);
3. ONE ``applications LEFT JOIN candidate_stages (ACTIVE)`` fetch → every card with
   its current stage position in a single statement (one ACTIVE row per app → no
   row multiplication);
4. batched applicant identity lookup (contacts + avatars, two ``IN`` queries);
5. batched rollback-count lookup (one grouped query);
6. authoritative by-stage counts via ``dashboard_read`` (the ``proj_partner_pipeline``
   live read) so the column COUNTS are exact even when the rendered CARDS are
   capped.

Every card carries the applicant's real identity (owner decision 2026-07-10 — the
anonymous-apply + reveal handshake was removed); a card still never carries CV
text, the cover letter, screening answers, or scores — a kanban glance is minimal
by construction.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.application import job_read_facade
from app.modules.organization.application import org_reporting_facade
from app.modules.recruitment.api import presenters
from app.modules.recruitment.application import _shared, dashboard_read, stage_service
from app.modules.recruitment.domain import lifecycle, pipeline, scorecard
from app.modules.recruitment.domain.models import (
    Application,
    CandidateStage,
    PipelineStage,
    Scorecard,
)
from app.modules.student_profiles.application import avatar_facade
from app.modules.users.application import user_read_facade
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE

# Max candidate CARDS rendered across the whole board. The authoritative column
# COUNTS (``summary``/``column.count``) are always exact (cheap grouped aggregate);
# only the rendered cards are capped so a pathological job (thousands of
# applicants) cannot blow up one response. When exceeded, ``truncated=true`` and
# the newest applications by ``applied_at`` are kept. A future slice can add
# per-column cursor paging; V1 caps the board.
BOARD_CANDIDATE_CAP = 300

# Pre-pipeline bucket key/labels: applications still ``submitted`` (or a legacy
# ``under_review`` with no ACTIVE stage row) live here so they are never lost.
_NEW_KEY = "new"
_NEW_LABELS = {"vi": "Hồ sơ mới", "en": "New applications"}


def _new_column_name(locale: str) -> str:
    return _NEW_LABELS.get(locale, _NEW_LABELS["vi"])


async def _load_org_scoped_job(
    session: AsyncSession, *, principal: Principal, job_id: uuid.UUID
) -> job_read_facade.JobRef:
    """Load a job the caller may read as a partner of its owning org (else ``404``).

    Mirrors ``apply_service.list_job_applications``: a cross-org or non-partner
    caller is indistinguishable from a missing job (``404``, never ``403``).
    """

    job = await job_read_facade.get_job_ref(session, job_id)
    if job is None:
        raise ResourceNotFoundError()
    if not principal.is_superadmin and (principal.org_id is None or principal.org_id != job.org_id):
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=job.org_id)
    return job


async def _board_stages(session: AsyncSession, *, org_id: uuid.UUID) -> list[PipelineStage]:
    """The ordered template stages = the kanban columns (lazily seeded if absent)."""

    tmpl = await stage_service.ensure_org_default_template(session, org_id=org_id)
    return await stage_service._template_stages(session, template_id=tmpl.id)


async def _fetch_cards(
    session: AsyncSession, *, job_id: uuid.UUID
) -> tuple[list[tuple[Application, uuid.UUID | None, object]], bool]:
    """ONE statement: active-outcome apps + their ACTIVE stage position.

    LEFT JOIN keeps ``submitted`` apps (no ACTIVE row → ``stage_id`` is ``None`` →
    the pre-pipeline bucket). Terminal outcomes (``rejected`` / ``withdrawn``) are
    excluded — a kanban board shows only candidates currently in the pipeline.
    Returns ``(rows, truncated)``.
    """

    stmt = (
        select(Application, CandidateStage.stage_id, CandidateStage.entered_at)
        .outerjoin(
            CandidateStage,
            and_(
                CandidateStage.application_id == Application.id,
                CandidateStage.status == pipeline.STAGE_ACTIVE,
            ),
        )
        .where(
            Application.job_id == job_id,
            Application.deleted_at.is_(None),
            Application.status.in_(tuple(lifecycle.ACTIVE_STATUSES)),
        )
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .limit(BOARD_CANDIDATE_CAP + 1)
    )
    rows = list((await session.execute(stmt)).all())
    truncated = len(rows) > BOARD_CANDIDATE_CAP
    if truncated:
        rows = rows[:BOARD_CANDIDATE_CAP]
    return [(r[0], r[1], r[2]) for r in rows], truncated


async def _batch_users(
    session: AsyncSession, *, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, user_read_facade.UserContact]:
    if not user_ids:
        return {}
    return await user_read_facade.get_user_contacts(session, user_ids)


async def _batch_assignees(
    session: AsyncSession, *, org_id: uuid.UUID, membership_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict]:
    """Resolve ``{membership_id: assignee_block}`` for the assigned recruiters.

    ONE batched org-facade lookup (membership query + names) for the whole board —
    independent of candidate count. Reads through ``org_reporting_facade`` so the
    recruitment module never imports the ``Membership`` ORM directly. The assignee
    is PARTNER staff (never the candidate) so the name is always shown; the block
    matches ``presenters.partner_application``'s ``assignee`` shape.
    """

    if not membership_ids:
        return {}
    briefs = await org_reporting_facade.member_briefs(
        session, org_id=org_id, membership_ids=membership_ids
    )
    return {
        mid: {
            "membership_id": str(brief.membership_id),
            "user_id": str(brief.user_id),
            "display_name": brief.display_name,
        }
        for mid, brief in briefs.items()
    }


async def _batch_rollback_counts(
    session: AsyncSession, *, application_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not application_ids:
        return {}
    rows = (
        await session.execute(
            select(CandidateStage.application_id, func.count())
            .where(
                CandidateStage.application_id.in_(set(application_ids)),
                CandidateStage.status == pipeline.STAGE_ROLLED_BACK,
            )
            .group_by(CandidateStage.application_id)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


async def _batch_stage_evaluations(
    session: AsyncSession,
    *,
    current_stage_by_app: dict[uuid.UUID, uuid.UUID],
    required_by_stage: dict[uuid.UUID, str],
) -> dict[uuid.UUID, dict]:
    """Partner-only scorecard summary per card, for each card's CURRENT stage.

    ONE grouped query over ``scorecards`` for all card application ids (no N+1).
    Only submitted (non-withdrawn) rows on the card's CURRENT stage count, so the
    summary matches the advance gate. Returns ``{application_id: evaluation}``;
    every summary is PARTNER-ONLY and never reaches the student projection.
    """

    if not current_stage_by_app:
        return {}
    rows = (
        await session.execute(
            select(
                Scorecard.application_id,
                Scorecard.stage_id,
                Scorecard.recommendation,
                Scorecard.overall_score,
            ).where(
                Scorecard.application_id.in_(set(current_stage_by_app)),
                Scorecard.status == scorecard.SCORECARD_SUBMITTED,
            )
        )
    ).all()

    # Bucket submitted scorecards by (application_id) but only those on the card's
    # CURRENT stage (a scorecard left on a now-passed stage does not gate advance).
    buckets: dict[uuid.UUID, list[tuple[str, object]]] = {}
    for app_id, stage_id, recommendation, overall in rows:
        if current_stage_by_app.get(app_id) == stage_id:
            buckets.setdefault(app_id, []).append((recommendation, overall))

    out: dict[uuid.UUID, dict] = {}
    for app_id, current_stage_id in current_stage_by_app.items():
        required = scorecard.required_for_action(required_by_stage.get(current_stage_id, ""))
        cards = buckets.get(app_id, [])
        submitted_count = len(cards)
        overalls = [float(o) for _r, o in cards if isinstance(o, (int, float, Decimal))]
        rec_summary = dict.fromkeys(scorecard.RECOMMENDATION_ORDER, 0)
        for recommendation, _o in cards:
            if recommendation in rec_summary:
                rec_summary[recommendation] += 1
        out[app_id] = {
            "submitted_count": submitted_count,
            "required": required,
            "gate_met": scorecard.gate_met(submitted_count, required),
            "avg_overall": (round(sum(overalls) / len(overalls), 1) if overalls else None),
            "recommendation_summary": rec_summary,
        }
    return out


def _stage_summary(stage: PipelineStage) -> dict:
    return {
        "id": str(stage.id),
        "name": stage.name,
        "stage_type": stage.stage_type,
        "sort_order": stage.sort_order,
        "is_terminal": stage.is_terminal,
        "candidate_visible": stage.candidate_visible,
        # Partner-only: the kanban renders the scorecard gate on a ``scorecard``
        # column (advance is blocked until a scorecard is submitted).
        "required_action": stage.required_action,
    }


async def get_job_pipeline_board(
    session: AsyncSession,
    *,
    principal: Principal,
    job_id: uuid.UUID,
    locale: str = "vi",
) -> dict:
    """Build the full kanban board for one partner job (org-scoped, anonymity-safe)."""

    job = await _load_org_scoped_job(session, principal=principal, job_id=job_id)
    stages = await _board_stages(session, org_id=job.org_id)
    template_id = str(stages[0].template_id) if stages else None

    cards_raw, truncated = await _fetch_cards(session, job_id=job.id)
    app_ids = [app.id for app, _stage_id, _entered in cards_raw]

    # Every card carries the applicant's real identity (contacts + avatars) — TWO
    # batched facade lookups for the whole board, independent of candidate count.
    applicant_ids = [app.applicant_id for app, _stage_id, _entered in cards_raw]
    users = await _batch_users(session, user_ids=applicant_ids)
    avatars = await avatar_facade.avatar_urls_for(session, applicant_ids)
    rollback_counts = await _batch_rollback_counts(session, application_ids=app_ids)
    # Candidate owner (assignee) per card — ONE batched org-facade lookup for the
    # whole board (empty set → no query, so the board's bounded-query budget holds).
    assignees = await _batch_assignees(
        session,
        org_id=job.org_id,
        membership_ids=[
            app.assigned_to_membership_id
            for app, _stage_id, _entered in cards_raw
            if app.assigned_to_membership_id is not None
        ],
    )

    # Partner-only scorecard summary per card (current stage) — ONE batched query.
    required_by_stage = {stage.id: stage.required_action for stage in stages}
    current_stage_by_app = {
        app.id: stage_id
        for app, stage_id, _entered in cards_raw
        if stage_id is not None and stage_id in required_by_stage
    }
    evaluations = await _batch_stage_evaluations(
        session,
        current_stage_by_app=current_stage_by_app,
        required_by_stage=required_by_stage,
    )

    # Group cards into columns. ``stage_id is None`` → pre-pipeline "new" bucket;
    # a stage id outside the current template (should not happen with the single V1
    # template) also falls back to "new" so no candidate is ever dropped.
    stage_ids = {stage.id for stage in stages}
    new_cards: list[dict] = []
    by_stage_cards: dict[uuid.UUID, list[dict]] = {stage.id: [] for stage in stages}

    for app, stage_id, entered_at in cards_raw:
        applicant = presenters.applicant_block(
            app,
            user=users.get(app.applicant_id),
            avatar_url=avatars.get(app.applicant_id),
        )
        card = presenters.partner_board_card(
            app,
            applicant=applicant,
            stage_id=str(stage_id) if stage_id is not None else None,
            position=None,
            entered_at=entered_at if stage_id is not None else None,
            rollback_count=rollback_counts.get(app.id, 0),
            evaluation=evaluations.get(app.id),
            assignee=assignees.get(app.assigned_to_membership_id)
            if app.assigned_to_membership_id is not None
            else None,
            locale=locale,
        )
        if stage_id is not None and stage_id in stage_ids:
            by_stage_cards[stage_id].append(card)
        else:
            card["stage_id"] = None
            card["entered_at"] = None
            new_cards.append(card)

    # Authoritative column COUNTS (exact even when cards are capped) — the
    # proj_partner_pipeline live read derived from candidate_stages ACTIVE rows.
    counts = await dashboard_read.pipeline_counts_for_job(session, job_id=job.id)
    by_stage_counts: dict[str, int] = counts["by_stage"]

    # Fill ``position`` now that the stage→sort_order map is known.
    sort_by_stage = {stage.id: stage.sort_order for stage in stages}
    for stage in stages:
        for card in by_stage_cards[stage.id]:
            card["position"] = sort_by_stage[stage.id]

    columns: list[dict] = [
        {
            "key": _NEW_KEY,
            "stage_id": None,
            "name": _new_column_name(locale),
            "sort_order": 0,
            "candidate_visible": True,
            "count": counts["new"],
            "candidates": new_cards,
        }
    ]
    for stage in stages:
        columns.append(
            {
                "key": f"stage:{stage.id}",
                "stage_id": str(stage.id),
                "name": stage.name,
                "stage_type": stage.stage_type,
                "sort_order": stage.sort_order,
                "candidate_visible": stage.candidate_visible,
                "is_terminal": stage.is_terminal,
                "count": by_stage_counts.get(str(stage.id), 0),
                "candidates": by_stage_cards[stage.id],
            }
        )

    return {
        "job": {"id": str(job.id), "title": job.title},
        "template_id": template_id,
        "stages": [_stage_summary(stage) for stage in stages],
        "columns": columns,
        "summary": counts,
        "truncated": truncated,
        "candidate_cap": BOARD_CANDIDATE_CAP,
    }
