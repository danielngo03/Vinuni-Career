"""Scorecard evaluation service (ADR-0005 §2/§3/§6).

Layered on the shipped ADR-0004 stage engine. A scorecard is ONE reviewer's
evaluation of ONE candidate at ONE pipeline stage:

- :func:`submit_scorecard` — submit / UPSERT the caller's scorecard for the
  candidate's CURRENT ACTIVE stage (one ACTIVE scorecard per
  ``(application, stage, reviewer)``); recomputes ``overall_score``, bumps the
  per-scorecard ``version`` on edit, audits every write.
- :func:`withdraw_scorecard` — author-only soft ``status -> withdrawn`` (kept for
  audit; excluded from the gate + every aggregate).
- :func:`list_scorecards` — the partner read with the ANCHORING-bias rule
  (BUSINESS_LOGIC §3.4): a caller sees OTHER reviewers' scores only AFTER
  submitting their own for that stage; before that, only the submitted COUNT.
- :func:`evaluate_advance_gate` — reused by the GET aggregate AND the
  ``stage_service`` advance hook (``submitted >= 1`` on a ``scorecard`` stage).

RBAC + tenant isolation reuse ``decision_service._load_partner_application`` (the
cross-org / non-partner ``404`` gate) PLUS the scorecard permission codes. Every
write is audited; the reason/scores live in audit metadata only.

VISIBILITY (NON-NEGOTIABLE, ADR-0005 §2): scorecards — existence, scores,
recommendation, comment, aggregate — are PARTNER-INTERNAL and NEVER appear in the
student application projection, any student notification, or any email body (same
privacy class as ``rejection_reason``). No scorecard carries a student-identity
field; the reveal handshake stays the only identity path.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.recruitment.application import _shared
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    IllegalApplicationTransitionError,
    InvalidApplicationFieldError,
)
from app.modules.recruitment.domain import interview, lifecycle, scorecard
from app.modules.recruitment.domain.models import (
    PipelineStage,
    Scorecard,
    ScorecardScore,
)
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

# Scorecard permission codes (ADR-0005 §2) — default to partner members in V1
# (a partner admin's ``*:*`` grant covers them). Resource ``scorecards`` keeps
# them distinct from the broader ``applications:*`` read/write surface and
# matches the catalog noun in ``docs/PARTNER_RBAC_ANALYTICS_SPEC.md``.
_SCORECARD_RESOURCE = "scorecards"
_PERM_SUBMIT = "submit"
_PERM_READ = "read"

_AUDIT_SUBMITTED = "application.scorecard_submitted"
_AUDIT_UPDATED = "application.scorecard_updated"
_AUDIT_WITHDRAWN = "application.scorecard_withdrawn"


# --------------------------------------------------------------------------- #
# Validation (defensive — Pydantic guards the HTTP boundary)                   #
# --------------------------------------------------------------------------- #


def _validate_submission(
    *, recommendation: str, scores: Sequence[dict]
) -> dict[str, int]:
    """Validate recommendation + the full criteria set; return ``{key: score}``.

    Raises :class:`InvalidApplicationFieldError` (422) for a bad/missing
    recommendation, an unknown / duplicate / incomplete criteria set, or a score
    outside ``1..5``. Mirrors the rollback-reason defensive guard for non-HTTP
    callers and enforces the "all criteria present" rule Pydantic can't express.
    """

    if recommendation not in scorecard.RECOMMENDATIONS:
        raise InvalidApplicationFieldError(field="recommendation")

    clean: dict[str, int] = {}
    for item in scores:
        key = item.get("criterion_key")
        value = item.get("score")
        if key not in scorecard.DEFAULT_CRITERION_KEYS or key in clean:
            raise InvalidApplicationFieldError(field="criterion_key")
        if not scorecard.is_valid_score(value):
            raise InvalidApplicationFieldError(field="score")
        clean[key] = int(value)  # type: ignore[arg-type]

    if set(clean) != scorecard.DEFAULT_CRITERION_KEYS:
        raise InvalidApplicationFieldError(field="scores")
    # Re-key in the canonical DEFAULT_CRITERIA order for a stable response shape.
    return {c["key"]: clean[c["key"]] for c in scorecard.DEFAULT_CRITERIA}


# --------------------------------------------------------------------------- #
# Repository helpers                                                           #
# --------------------------------------------------------------------------- #


async def _reviewer_active_scorecard(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    stage_id: uuid.UUID,
    reviewer_id: uuid.UUID,
) -> Scorecard | None:
    """The caller's current ACTIVE (submitted) scorecard for this stage, if any."""

    return (
        await session.execute(
            select(Scorecard).where(
                Scorecard.application_id == application_id,
                Scorecard.stage_id == stage_id,
                Scorecard.submitted_by_user_id == reviewer_id,
                Scorecard.status == scorecard.SCORECARD_SUBMITTED,
            )
        )
    ).scalars().first()


async def _submitted_scorecards(
    session: AsyncSession, *, application_id: uuid.UUID, stage_id: uuid.UUID
) -> list[Scorecard]:
    return list(
        (
            await session.execute(
                select(Scorecard)
                .where(
                    Scorecard.application_id == application_id,
                    Scorecard.stage_id == stage_id,
                    Scorecard.status == scorecard.SCORECARD_SUBMITTED,
                )
                .order_by(Scorecard.submitted_at, Scorecard.id)
            )
        ).scalars().all()
    )


async def _submitted_count(
    session: AsyncSession, *, application_id: uuid.UUID, stage_id: uuid.UUID
) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(Scorecard)
            .where(
                Scorecard.application_id == application_id,
                Scorecard.stage_id == stage_id,
                Scorecard.status == scorecard.SCORECARD_SUBMITTED,
            )
        )
    ).scalar_one()


async def _scores_for(
    session: AsyncSession, *, scorecard_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, int]]:
    if not scorecard_ids:
        return {}
    rows = (
        await session.execute(
            select(
                ScorecardScore.scorecard_id,
                ScorecardScore.criterion_key,
                ScorecardScore.score,
            ).where(ScorecardScore.scorecard_id.in_(set(scorecard_ids)))
        )
    ).all()
    out: dict[uuid.UUID, dict[str, int]] = {sid: {} for sid in scorecard_ids}
    for sid, key, score in rows:
        out.setdefault(sid, {})[key] = score
    # Re-order each map by DEFAULT_CRITERIA for a stable response.
    ordered: dict[uuid.UUID, dict[str, int]] = {}
    for sid, mapping in out.items():
        ordered[sid] = {
            c["key"]: mapping[c["key"]]
            for c in scorecard.DEFAULT_CRITERIA
            if c["key"] in mapping
        }
    return ordered


async def _submitted_assignee_scorecards(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    stage_id: uuid.UUID,
    assignee_ids: set[uuid.UUID],
) -> list[Scorecard]:
    """Submitted (non-withdrawn) scorecards for the stage authored by an ASSIGNEE.

    Only assignee scorecards count toward the upgraded ADR-0006 gate; a non-assignee
    partner member may still submit a scorecard (ADR-0005 RBAC), but it does not move
    the ``required``/``avg`` denominator.
    """

    if not assignee_ids:
        return []
    return list(
        (
            await session.execute(
                select(Scorecard)
                .where(
                    Scorecard.application_id == application_id,
                    Scorecard.stage_id == stage_id,
                    Scorecard.status == scorecard.SCORECARD_SUBMITTED,
                    Scorecard.submitted_by_user_id.in_(assignee_ids),
                )
                .order_by(Scorecard.submitted_at, Scorecard.id)
            )
        ).scalars().all()
    )


async def _open_interview_assignee_ids(
    session: AsyncSession, *, application_id: uuid.UUID, stage_id: uuid.UUID
) -> set[uuid.UUID]:
    """Assignee ``user_id`` set on the stage's OPEN interview (empty when none).

    Lazy import keeps ``scorecard_service`` -> ``interview_service`` one-directional
    (the interview service composes the gate, not the reverse).
    """

    from app.modules.recruitment.application import interview_service

    return await interview_service.open_interview_assignee_ids(
        session, application_id=application_id, stage_id=stage_id
    )


async def _gate_inputs(
    session: AsyncSession, *, application_id: uuid.UUID, stage: PipelineStage
) -> tuple[list[Scorecard], int]:
    """The ``(counted_cards, required)`` pair for a scorecard-gated stage.

    When the stage has an OPEN interview with assignees, ``required`` is the assignee
    count and only assignee scorecards count (ADR-0006). Otherwise it falls back to
    the ADR-0005 behavior: ``required = 1`` and any submitted scorecard counts.
    """

    assignee_ids = await _open_interview_assignee_ids(
        session, application_id=application_id, stage_id=stage.id
    )
    if assignee_ids:
        cards = await _submitted_assignee_scorecards(
            session,
            application_id=application_id,
            stage_id=stage.id,
            assignee_ids=assignee_ids,
        )
        return cards, len(assignee_ids)
    cards = await _submitted_scorecards(
        session, application_id=application_id, stage_id=stage.id
    )
    return cards, scorecard.required_for_action(stage.required_action)


async def _load_scorecard(
    session: AsyncSession, *, scorecard_id: uuid.UUID, application_id: uuid.UUID
) -> Scorecard | None:
    return (
        await session.execute(
            select(Scorecard).where(
                Scorecard.id == scorecard_id,
                Scorecard.application_id == application_id,
            )
        )
    ).scalars().first()


# --------------------------------------------------------------------------- #
# Aggregation + anchoring                                                      #
# --------------------------------------------------------------------------- #


def _recommendation_summary(cards: Sequence[Scorecard]) -> dict[str, int]:
    summary = dict.fromkeys(scorecard.RECOMMENDATION_ORDER, 0)
    for card in cards:
        if card.recommendation in summary:
            summary[card.recommendation] += 1
    return summary


def _avg_overall(cards: Sequence[Scorecard]) -> float | None:
    overalls = [float(c.overall_score) for c in cards if c.overall_score is not None]
    if not overalls:
        return None
    return round(sum(overalls) / len(overalls), 1)


def _by_criterion(
    cards: Sequence[Scorecard], scores_by_card: dict[uuid.UUID, dict[str, int]]
) -> dict[str, float]:
    totals: dict[str, list[int]] = {c["key"]: [] for c in scorecard.DEFAULT_CRITERIA}
    for card in cards:
        for key, value in scores_by_card.get(card.id, {}).items():
            totals.setdefault(key, []).append(value)
    return {
        key: round(sum(values) / len(values), 1)
        for key, values in totals.items()
        if values
    }


def _build_aggregate(
    cards: Sequence[Scorecard],
    scores_by_card: dict[uuid.UUID, dict[str, int]],
    *,
    required: int,
    reveal_scores: bool,
) -> dict:
    """Aggregate over the SUBMITTED scorecards for one stage.

    ``reveal_scores=False`` (the anchoring guard — caller has not submitted their
    own yet) exposes ONLY the round-progress counters, never any score-derived
    field, so a reviewer cannot be anchored by peers' evaluations.
    """

    submitted_count = len(cards)
    base: dict[str, object] = {
        "submitted_count": submitted_count,
        "required": required,
        "gate_met": scorecard.gate_met(submitted_count, required),
    }
    if not reveal_scores:
        base.update(
            {"avg_overall": None, "recommendation_summary": {}, "by_criterion": {}}
        )
        return base
    base.update(
        {
            "avg_overall": _avg_overall(cards),
            "recommendation_summary": _recommendation_summary(cards),
            "by_criterion": _by_criterion(cards, scores_by_card),
        }
    )
    return base


# --------------------------------------------------------------------------- #
# Advance gate (reused by the GET aggregate + the stage_service advance hook)  #
# --------------------------------------------------------------------------- #


def _threshold_of(stage: PipelineStage) -> float | None:
    return float(stage.score_threshold) if stage.score_threshold is not None else None


async def evaluate_advance_gate(
    session: AsyncSession, *, application_id: uuid.UUID, stage: PipelineStage
) -> scorecard.AdvanceGate:
    """Whether the scorecard gate to advance OUT of ``stage`` is met (ADR-0006).

    - ``scorecard``: ``required`` = the count of assignees on the stage's OPEN
      interview when present (all assigned interviewers must submit), else the
      ADR-0005 fallback ``1``; ``submitted`` is the count of submitted assignee
      scorecards (else any submitted scorecard).
    - ``score_threshold``: the SAME assignee-count gate FIRST, then the average gate
      (``mean(overall_score) >= stage.score_threshold``).
    - other actions: ``required = 0`` -> trivially allowed.

    Pure read — never raises. The advance hook maps a non-allowed gate to the precise
    error via ``gate.reason`` (``scorecard_required`` / ``score_below_threshold``).
    """

    if scorecard.required_for_action(stage.required_action) == 0:
        return scorecard.AdvanceGate(allowed=True, submitted=0, required=0)

    cards, required = await _gate_inputs(
        session, application_id=application_id, stage=stage
    )
    submitted = len(cards)
    count_met = scorecard.gate_met(submitted, required)

    if stage.required_action != interview.ACTION_SCORE_THRESHOLD:
        return scorecard.AdvanceGate(
            allowed=count_met,
            submitted=submitted,
            required=required,
            reason=None if count_met else "scorecard_required",
        )

    # score_threshold: assignee-count gate first, then the average gate.
    threshold = _threshold_of(stage)
    avg = _avg_overall(cards)
    if not count_met:
        return scorecard.AdvanceGate(
            allowed=False,
            submitted=submitted,
            required=required,
            avg_overall=avg,
            threshold=threshold,
            reason="scorecard_required",
        )
    avg_ok = interview.avg_threshold_met(avg, threshold)
    return scorecard.AdvanceGate(
        allowed=avg_ok,
        submitted=submitted,
        required=required,
        avg_overall=avg,
        threshold=threshold,
        reason=None if avg_ok else "score_below_threshold",
    )


async def stage_evaluation_summary(
    session: AsyncSession, *, application_id: uuid.UUID, stage: PipelineStage
) -> dict:
    """Partner-only evaluation summary for a card's CURRENT stage (board glance).

    ``{submitted_count, required, gate_met, avg_overall, threshold,
    recommendation_summary}`` — ``required`` is assignee-derived and ``gate_met``
    honors the ``score_threshold`` average gate (ADR-0006). PARTNER-INTERNAL — the
    caller (``stage_service._pipeline_block``) merges it onto the partner projection
    only; it NEVER reaches the student projection.
    """

    if scorecard.required_for_action(stage.required_action) == 0:
        cards = await _submitted_scorecards(
            session, application_id=application_id, stage_id=stage.id
        )
        return {
            "submitted_count": len(cards),
            "required": 0,
            "gate_met": True,
            "avg_overall": _avg_overall(cards),
            "threshold": None,
            "recommendation_summary": _recommendation_summary(cards),
        }

    cards, required = await _gate_inputs(
        session, application_id=application_id, stage=stage
    )
    threshold = _threshold_of(stage)
    avg = _avg_overall(cards)
    count_met = scorecard.gate_met(len(cards), required)
    if stage.required_action == interview.ACTION_SCORE_THRESHOLD:
        gate_met = count_met and interview.avg_threshold_met(avg, threshold)
    else:
        gate_met = count_met
    return {
        "submitted_count": len(cards),
        "required": required,
        "gate_met": gate_met,
        "avg_overall": avg,
        "threshold": threshold,
        "recommendation_summary": _recommendation_summary(cards),
    }


# --------------------------------------------------------------------------- #
# Reads                                                                        #
# --------------------------------------------------------------------------- #


async def _resolve_stage(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    stage_id: uuid.UUID | None,
) -> tuple[uuid.UUID | None, str | None]:
    """Resolve the (stage_id, required_action) to scope a read by.

    Defaults to the candidate's CURRENT ACTIVE stage. Returns ``(None, None)`` when
    no stage applies yet (pre-pipeline) — the read is then an empty result.
    """

    from app.modules.recruitment.application import stage_service

    if stage_id is not None:
        stage = await stage_service._load_stage(session, stage_id=stage_id)
        if stage is None:
            return None, None
        return stage.id, stage.required_action
    active = await stage_service._active_stage(session, application_id=application_id)
    if active is None:
        return None, None
    stage = await stage_service._load_stage(session, stage_id=active.stage_id)
    if stage is None:
        return None, None
    return stage.id, stage.required_action


async def list_scorecards(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    stage_id: uuid.UUID | None = None,
    locale: str = "vi",
) -> dict:
    """Partner read of the scorecards for one stage, with the ANCHORING rule.

    ``mine`` is always the caller's own scorecard; ``scorecards`` (others') appear
    ONLY after the caller has submitted their own for the stage; the ``aggregate``
    score-derived fields are likewise withheld until the caller submits.
    """

    from app.modules.recruitment.application import decision_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _SCORECARD_RESOURCE, _PERM_READ, resource_org_id=app.org_id
    )
    return await _read_stage_scorecards(
        session,
        principal=principal,
        application_id=app.id,
        stage_id=stage_id,
        locale=locale,
    )


async def _read_stage_scorecards(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    stage_id: uuid.UUID | None,
    locale: str,
) -> dict:
    from app.modules.recruitment.api import presenters

    resolved_stage_id, required_action = await _resolve_stage(
        session, application_id=application_id, stage_id=stage_id
    )
    if resolved_stage_id is None:
        return {
            "stage_id": None,
            "mine": None,
            "scorecards": [],
            "aggregate": _build_aggregate([], {}, required=0, reveal_scores=False),
            "criteria": presenters.scorecard_criteria(locale=locale),
        }

    required = scorecard.required_for_action(required_action or "")
    submitted = await _submitted_scorecards(
        session, application_id=application_id, stage_id=resolved_stage_id
    )
    scores_by_card = await _scores_for(
        session, scorecard_ids=[s.id for s in submitted]
    )
    mine = next(
        (s for s in submitted if s.submitted_by_user_id == principal.user_id), None
    )
    caller_submitted = mine is not None
    others = [s for s in submitted if s.submitted_by_user_id != principal.user_id]

    mine_view = (
        presenters.scorecard_detail(
            mine, scores=scores_by_card.get(mine.id, {}), is_mine=True, locale=locale
        )
        if mine is not None
        else None
    )
    # Anchoring (BUSINESS_LOGIC §3.4): others' scores ONLY after the caller submits.
    others_view = (
        [
            presenters.scorecard_detail(
                s, scores=scores_by_card.get(s.id, {}), is_mine=False, locale=locale
            )
            for s in others
        ]
        if caller_submitted
        else []
    )
    aggregate = _build_aggregate(
        submitted, scores_by_card, required=required, reveal_scores=caller_submitted
    )
    return {
        "stage_id": str(resolved_stage_id),
        "mine": mine_view,
        "scorecards": others_view,
        "aggregate": aggregate,
        "criteria": presenters.scorecard_criteria(locale=locale),
    }


# --------------------------------------------------------------------------- #
# Writes                                                                       #
# --------------------------------------------------------------------------- #


async def submit_scorecard(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    recommendation: str,
    scores: Sequence[dict],
    comment: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Submit / UPSERT the caller's scorecard for the candidate's current stage."""

    from app.modules.recruitment.application import decision_service, stage_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _SCORECARD_RESOURCE, _PERM_SUBMIT, resource_org_id=app.org_id
    )

    clean_scores = _validate_submission(recommendation=recommendation, scores=scores)

    # A scorecard targets the candidate's CURRENT ACTIVE stage; only meaningful
    # while the application is actively in the pipeline (under_review).
    if app.status != lifecycle.UNDER_REVIEW:
        raise IllegalApplicationTransitionError(event="scorecard")
    active = await stage_service._active_stage(
        session, application_id=app.id, lock=True
    )
    if active is None:
        raise IllegalApplicationTransitionError(event="scorecard")
    stage_id = active.stage_id

    clean_comment = (comment or None) and comment.strip() or None
    overall = scorecard.overall_of(clean_scores)

    # ADR-0006 auto-link: bind the scorecard to the stage's OPEN interview when one
    # exists (nullable otherwise). Lazy import keeps the dependency one-directional.
    from app.modules.recruitment.application import interview_service

    interview_id = await interview_service.open_interview_id(
        session, application_id=app.id, stage_id=stage_id
    )

    existing = await _reviewer_active_scorecard(
        session, application_id=app.id, stage_id=stage_id, reviewer_id=principal.user_id  # type: ignore[arg-type]
    )
    if existing is None:
        sc = Scorecard(
            application_id=app.id,
            stage_id=stage_id,
            org_id=app.org_id,
            submitted_by_user_id=principal.user_id,
            interview_id=interview_id,
            recommendation=recommendation,
            overall_score=overall,
            comment=clean_comment,
            status=scorecard.SCORECARD_SUBMITTED,
            version=1,
            submitted_at=_shared.now(),
        )
        session.add(sc)
        await session.flush()
        _add_scores(session, scorecard_id=sc.id, scores=clean_scores)
        audit_action = _AUDIT_SUBMITTED
    else:
        # Optimistic concurrency on the EDIT path (a stale editor -> 409).
        if version is not None and version != existing.version:
            raise ApplicationVersionConflictError()
        sc = existing
        sc.interview_id = interview_id
        sc.recommendation = recommendation
        sc.overall_score = overall
        sc.comment = clean_comment
        sc.version += 1
        await session.execute(
            delete(ScorecardScore).where(ScorecardScore.scorecard_id == sc.id)
        )
        await session.flush()
        _add_scores(session, scorecard_id=sc.id, scores=clean_scores)
        audit_action = _AUDIT_UPDATED

    await session.flush()
    await write_audit(
        session,
        action=audit_action,
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        # Scores/recommendation stay in audit metadata only — never user-facing.
        after={
            "scorecard_id": str(sc.id),
            "stage_id": str(stage_id),
            "recommendation": recommendation,
            "overall_score": str(overall) if overall is not None else None,
            "version": sc.version,
        },
    )
    await session.commit()

    return await _read_stage_scorecards(
        session,
        principal=principal,
        application_id=app.id,
        stage_id=stage_id,
        locale=locale,
    )


def _add_scores(
    session: AsyncSession, *, scorecard_id: uuid.UUID, scores: dict[str, int]
) -> None:
    for key, value in scores.items():
        session.add(
            ScorecardScore(scorecard_id=scorecard_id, criterion_key=key, score=value)
        )


async def withdraw_scorecard(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    scorecard_id: uuid.UUID,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Author-only soft withdraw (``status -> withdrawn``); excluded from gate."""

    from app.modules.recruitment.application import decision_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )
    permission_checker.require(
        principal, _SCORECARD_RESOURCE, _PERM_SUBMIT, resource_org_id=app.org_id
    )

    sc = await _load_scorecard(
        session, scorecard_id=scorecard_id, application_id=app.id
    )
    # Author-only: another reviewer (or a missing scorecard) is indistinguishable
    # from not-found (404, never 403) — a reviewer may only touch their own.
    if sc is None or sc.submitted_by_user_id != principal.user_id:
        raise ResourceNotFoundError()

    stage_id = sc.stage_id
    if sc.status != scorecard.SCORECARD_WITHDRAWN:
        sc.status = scorecard.SCORECARD_WITHDRAWN
        sc.version += 1
        await session.flush()
        await write_audit(
            session,
            action=_AUDIT_WITHDRAWN,
            resource_type="application",
            resource_id=app.id,
            context=_shared.audit_ctx(principal, ctx),
            after={"scorecard_id": str(sc.id), "stage_id": str(stage_id)},
        )
        await session.commit()

    return await _read_stage_scorecards(
        session,
        principal=principal,
        application_id=app.id,
        stage_id=stage_id,
        locale=locale,
    )
