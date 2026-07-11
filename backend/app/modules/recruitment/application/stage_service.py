"""Pipeline stage engine — ``/advance`` + ``/rollback`` on ``candidate_stages``.

Layered on the shipped Phase-1.5 decision subset (``decision_service``) per
ADR-0004 §2/§6. The fine pipeline position lives entirely in ``candidate_stages``
(append-only history, one ACTIVE row per application); the coarse application
outcome stays on ``applications.status`` and is only meaningful while
``status = under_review``.

Two integration seams with the shipped subset (no duplicated logic):

- ``ensure_pipeline_entry`` — called by ``decision_service.review_application``;
  lazily materializes the stage-1 row at first ``review`` (idempotent).
- ``close_open_stage_on_reject`` — called by ``decision_service.reject_application``;
  closes the open stage row (status REJECTED) on the terminal exit.

Invariants are IDENTICAL to the decision subset and reuse the SAME machinery:
``decision_service._load_partner_application`` (404-not-403 cross-org gate +
``applications:read``), optimistic ``version`` (stale -> 409), illegal transition
-> 409, audit on every move (coded reason in metadata only),
``decision_service._notify_student`` neutral copy, and ``apply_service._partner_view``
anonymity (a stage move NEVER reveals the student — the reveal handshake stays the
only identity path).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.recruitment.application import _shared
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    IllegalApplicationTransitionError,
    InvalidApplicationFieldError,
    RollbackLimitReachedError,
    ScoreBelowThresholdError,
    ScorecardRequiredError,
)
from app.modules.recruitment.domain import interview, lifecycle, pipeline, scorecard, timeline
from app.modules.recruitment.domain.models import (
    Application,
    CandidateStage,
    PipelineStage,
    PipelineTemplate,
)
from app.shared.audit import write_audit
from app.shared.permissions import Principal

# Move event tokens (audit + illegal-transition payloads).
_ADVANCE = "advance"
_ROLLBACK = "rollback"


async def _emit_stage_changed(
    session: AsyncSession,
    *,
    app: Application,
    from_stage: PipelineStage | None,
    to_stage: PipelineStage,
    stage_row_id: uuid.UUID,
) -> None:
    """Best-effort ``system.stage_changed`` workflow trigger after a MANUAL advance.

    Fires the workflow engine so partner flows (e.g. "on stage change -> notify")
    can run. PII-safe payload (ids + stage metadata only). Idempotent per stage row
    (a re-fired trigger dedupes on the same key). A workflow-engine problem must
    NEVER fail the stage move, so this is fully guarded. Automation-driven moves
    pass ``emit_trigger=False`` and never reach here — that is what prevents a
    ``stage_changed`` -> auto-advance flow from cascading into itself.
    """

    from app.modules.workflow.application.trigger_service import dispatch_trigger

    try:
        await dispatch_trigger(
            session,
            trigger_type="system.stage_changed",
            payload={
                "application_id": str(app.id),
                "job_id": str(app.job_id),
                "org_id": str(app.org_id),
                "from_stage_id": str(from_stage.id) if from_stage is not None else None,
                "to_stage_id": str(to_stage.id),
                "to_order": to_stage.sort_order,
            },
            idempotency_key=f"stage_changed:{stage_row_id}",
            scope_org_id=app.org_id,
        )
    except Exception:  # noqa: BLE001 — workflow dispatch must never break a stage move
        pass


# --------------------------------------------------------------------------- #
# Default-template provider (lazy, idempotent)                                 #
# --------------------------------------------------------------------------- #


async def ensure_org_default_template(
    session: AsyncSession, *, org_id: uuid.UUID
) -> PipelineTemplate:
    """Return the org's immutable system-default template, creating it if absent.

    Idempotent: covers orgs created after migration ``0012`` seeded existing orgs
    (and the SQLite unit path, which never runs the migration). The 3 canonical
    stages are inserted from ``pipeline.DEFAULT_STAGES``.
    """

    tmpl = (
        await session.execute(
            select(PipelineTemplate).where(
                PipelineTemplate.org_id == org_id,
                PipelineTemplate.is_system.is_(True),
                PipelineTemplate.is_default.is_(True),
            )
        )
    ).scalar_one_or_none()
    if tmpl is not None:
        return tmpl

    tmpl = PipelineTemplate(
        org_id=org_id,
        name=pipeline.DEFAULT_TEMPLATE_NAME,
        is_default=True,
        is_system=True,
    )
    session.add(tmpl)
    await session.flush()
    for spec in pipeline.DEFAULT_STAGES:
        session.add(
            PipelineStage(
                template_id=tmpl.id,
                name=str(spec["name"]),
                stage_type=str(spec["stage_type"]),
                sort_order=int(spec["sort_order"]),  # type: ignore[call-overload]
                required_action=str(spec["required_action"]),
                is_terminal=bool(spec["is_terminal"]),
                candidate_visible=bool(spec["candidate_visible"]),
                automation_rules={},
            )
        )
    await session.flush()
    return tmpl


async def _template_stages(session: AsyncSession, *, template_id: uuid.UUID) -> list[PipelineStage]:
    return list(
        (
            await session.execute(
                select(PipelineStage)
                .where(PipelineStage.template_id == template_id)
                .order_by(PipelineStage.sort_order)
            )
        )
        .scalars()
        .all()
    )


async def _active_stage(
    session: AsyncSession, *, application_id: uuid.UUID, lock: bool = False
) -> CandidateStage | None:
    stmt = select(CandidateStage).where(
        CandidateStage.application_id == application_id,
        CandidateStage.status == pipeline.STAGE_ACTIVE,
    )
    if lock and _shared.use_for_update():
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalars().first()


async def _any_stage_exists(session: AsyncSession, *, application_id: uuid.UUID) -> bool:
    return (
        await session.execute(
            select(CandidateStage.id)
            .where(CandidateStage.application_id == application_id)
            .limit(1)
        )
    ).first() is not None


async def _rollback_count(session: AsyncSession, *, application_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count())
            .select_from(CandidateStage)
            .where(
                CandidateStage.application_id == application_id,
                CandidateStage.status == pipeline.STAGE_ROLLED_BACK,
            )
        )
    ).scalar_one()


async def _load_stage(session: AsyncSession, *, stage_id: uuid.UUID) -> PipelineStage | None:
    return (
        await session.execute(select(PipelineStage).where(PipelineStage.id == stage_id))
    ).scalar_one_or_none()


async def _stage_by_idempotency_key(
    session: AsyncSession, *, application_id: uuid.UUID, key: str
) -> CandidateStage | None:
    return (
        (
            await session.execute(
                select(CandidateStage).where(
                    CandidateStage.application_id == application_id,
                    CandidateStage.idempotency_key == key,
                )
            )
        )
        .scalars()
        .first()
    )


# --------------------------------------------------------------------------- #
# Integration seams with the shipped review/reject subset                      #
# --------------------------------------------------------------------------- #


async def ensure_pipeline_entry(
    session: AsyncSession, *, app: Application, principal: Principal
) -> bool:
    """Materialize the stage-1 ``candidate_stages`` row at first ``review``.

    Idempotent: a no-op when ANY stage row already exists for the application (so
    a re-review never resets an advanced candidate to stage 1). Returns ``True``
    only when a new ACTIVE stage-1 row was created. No commit — runs in the
    caller's transaction.
    """

    if await _any_stage_exists(session, application_id=app.id):
        return False
    tmpl = await ensure_org_default_template(session, org_id=app.org_id)
    stages = await _template_stages(session, template_id=tmpl.id)
    if not stages:
        return False
    first = stages[0]
    session.add(
        CandidateStage(
            application_id=app.id,
            stage_id=first.id,
            status=pipeline.STAGE_ACTIVE,
            entered_at=_shared.now(),
            entered_by=principal.user_id,
        )
    )
    await session.flush()
    return True


async def close_open_stage_on_reject(session: AsyncSession, *, app: Application) -> None:
    """Close the open ACTIVE stage row on the terminal reject exit (no new row)."""

    active = await _active_stage(session, application_id=app.id, lock=True)
    if active is None:
        return
    active.status = pipeline.STAGE_REJECTED
    active.exit_kind = pipeline.EXIT_REJECTED
    active.exited_at = _shared.now()
    await session.flush()


# --------------------------------------------------------------------------- #
# Projection (partner) — partner view + pipeline position                      #
# --------------------------------------------------------------------------- #


def _stage_summary(stage: PipelineStage) -> dict:
    return {
        "id": str(stage.id),
        "name": stage.name,
        "stage_type": stage.stage_type,
        "sort_order": stage.sort_order,
        "is_terminal": stage.is_terminal,
        "candidate_visible": stage.candidate_visible,
        # Partner-only: lets the kanban render the "scorecard required to advance"
        # gate on a ``scorecard`` stage before the advance call is attempted.
        "required_action": stage.required_action,
    }


async def _pipeline_block(session: AsyncSession, *, app: Application) -> dict:
    """The partner-facing pipeline position for an application (anonymity-safe).

    Contains ONLY stage metadata + position — never the student's identity. The
    redaction of the applicant is owned by ``apply_service._partner_view``; this
    block is merged on top of that view.
    """

    active = await _active_stage(session, application_id=app.id)
    if active is None:
        tmpl = await ensure_org_default_template(session, org_id=app.org_id)
        stages = await _template_stages(session, template_id=tmpl.id)
        return {
            "template_id": str(tmpl.id),
            "current_stage": None,
            "position": None,
            "total_stages": len(stages),
            "rollback_count": await _rollback_count(session, application_id=app.id),
            "stages": [_stage_summary(s) for s in stages],
        }
    stage = await _load_stage(session, stage_id=active.stage_id)
    assert stage is not None
    stages = await _template_stages(session, template_id=stage.template_id)
    # Partner-only scorecard evaluation summary for the CURRENT stage (ADR-0005 §6):
    # `gate_met` tells the partner whether the card is advance-blocked. This block
    # is merged onto the PARTNER projection only and NEVER reaches the student
    # projection. Lazy import avoids a stage_service <-> scorecard_service cycle.
    from app.modules.recruitment.application import interview_service, scorecard_service

    evaluation = await scorecard_service.stage_evaluation_summary(
        session, application_id=app.id, stage=stage
    )
    # Partner-only interview glance for the CURRENT stage (ADR-0006 §6) — the
    # scheduled interview's mode/time/status + assignee count. ``meeting_link`` is
    # deliberately ABSENT here (attendee-only surfaces). None when no open interview.
    open_iv = await interview_service._open_interview(
        session, application_id=app.id, stage_id=stage.id
    )
    interview_block = None
    if open_iv is not None:
        assignee_count = len(
            await interview_service._assignee_ids(session, interview_id=open_iv.id)
        )
        from app.modules.recruitment.api import presenters

        interview_block = presenters.interview_board_block(open_iv, assignee_count=assignee_count)
    # Partner-only offer glance (ADR-0007 §8): status + deadline at a glance. NO
    # salary on the board — open the offer detail to see comp. None when no offer.
    from app.modules.recruitment.application import offer_service

    offer_block = await offer_service.partner_offer_block(session, application_id=app.id)
    return {
        "template_id": str(stage.template_id),
        "current_stage": _stage_summary(stage),
        "position": stage.sort_order,
        "total_stages": len(stages),
        "rollback_count": await _rollback_count(session, application_id=app.id),
        # Partner-internal: why the candidate is being re-reviewed (last rollback).
        "current_reason": active.reason,
        # Partner-internal scorecard glance (never sent to the student).
        "evaluation": evaluation,
        # Partner-internal interview glance (never sent to the student).
        "interview": interview_block,
        # Partner-internal offer glance (never sent to the student; NO salary).
        "offer": offer_block,
        "stages": [_stage_summary(s) for s in stages],
    }


async def _projection(
    session: AsyncSession, *, app: Application, principal: Principal, locale: str
) -> dict:
    from app.modules.recruitment.application import decision_service

    view = await decision_service._partner_projection(
        session, app=app, principal=principal, locale=locale
    )
    view["pipeline"] = await _pipeline_block(session, app=app)
    return view


# --------------------------------------------------------------------------- #
# /advance                                                                     #
# --------------------------------------------------------------------------- #


async def _materialize_first_stage(
    session: AsyncSession,
    *,
    app: Application,
    principal: Principal,
    idempotency_key: str | None,
    ctx: RequestContext,
    locale: str,
    emit_trigger: bool = True,
) -> dict:
    """First-advance pipeline ENTRY for an under_review app with no ACTIVE row.

    Creates the stage-1 ACTIVE row (identical to ``ensure_pipeline_entry`` / the
    ``review`` hook) and LANDS the candidate at stage 1 — it deliberately does NOT
    step to stage 2 (that was the compounding bug). A subsequent advance moves
    1 -> 2 normally.

    Treated as a real stage move for consistency with ``/advance``: bumps the
    optimistic ``version``, carries the ``Idempotency-Key`` onto the new row (so an
    at-least-once retry of THIS entry dedupes via the up-front key lookup), audits
    ``application.stage_advanced`` (marked ``materialized`` with a null ``from``),
    and sends the neutral student notification ONLY when stage-1 is candidate-
    visible (ADR-0004 §4 — entering a visible stage). Anonymity is untouched.
    """

    from app.modules.recruitment.application import decision_service

    created = await ensure_pipeline_entry(session, app=app, principal=principal)
    new_row = await _active_stage(session, application_id=app.id, lock=True)
    if not created or new_row is None:
        # No ACTIVE row AND no row was materialized => stage history exists but is
        # fully closed, which is inconsistent for an under_review app. Fail closed
        # rather than silently advancing.
        raise IllegalApplicationTransitionError(event=_ADVANCE)
    first_stage = await _load_stage(session, stage_id=new_row.stage_id)
    assert first_stage is not None

    new_row.idempotency_key = idempotency_key
    app.last_status_at = _shared.now()
    app.version += 1
    await session.flush()

    await write_audit(
        session,
        action="application.stage_advanced",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "materialized": True,
            "from_stage": None,
            "from_order": None,
            "to_stage": str(first_stage.id),
            "to_order": first_stage.sort_order,
        },
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.STAGE_ADVANCED,
        actor_id=principal.user_id,
        metadata={"to_stage_name": first_stage.name, "materialized": True},
    )

    # Stage-1 is the candidate's FIRST pipeline stage; notify per the entering-a-
    # visible-stage rule (silent when stage-1 is not candidate-visible).
    if first_stage.candidate_visible:
        await decision_service._notify_student(
            session,
            app=app,
            template_key="application.stage_advanced",
            notif_type="recruitment.application_stage_advanced",
            dedupe_key=f"application.stage_advanced:{new_row.id}",
            feed_action_url=f"/student/applications/{app.id}?move={new_row.id}",
        )

    await session.commit()
    await session.refresh(app)
    if emit_trigger:
        await _emit_stage_changed(
            session, app=app, from_stage=None, to_stage=first_stage, stage_row_id=new_row.id
        )
    return await _projection(session, app=app, principal=principal, locale=locale)


async def advance_application_stage(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    version: int | None = None,
    idempotency_key: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
    emit_trigger: bool = True,
) -> dict:
    """Move the active stage row to the next stage by ``sort_order``.

    Pre-pipeline entry: if the under_review app has NO ACTIVE stage row, the first
    advance MATERIALIZES stage-1 and lands there (it does not compound into stage-2);
    a later advance then moves 1 -> 2. See :func:`_materialize_first_stage`.
    """

    from app.modules.recruitment.application import decision_service

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )

    # Idempotency-Key dedupe (BEFORE the version check): an at-least-once retry of
    # the SAME move returns the already-applied state instead of a 409/double move.
    if idempotency_key:
        prior = await _stage_by_idempotency_key(session, application_id=app.id, key=idempotency_key)
        if prior is not None:
            return await _projection(session, app=app, principal=principal, locale=locale)

    if version is not None and version != app.version:
        raise ApplicationVersionConflictError()

    # Advance is only meaningful while active in the pipeline (under_review).
    if app.status != lifecycle.UNDER_REVIEW:
        raise IllegalApplicationTransitionError(event=_ADVANCE)

    # First advance from a PRE-PIPELINE state (under_review but NO ACTIVE
    # candidate_stages row — e.g. an application that reached under_review before
    # the stage engine shipped, or any under_review app lacking a stage row) is the
    # pipeline-ENTRY move: it MATERIALIZES stage-1 and LANDS there. It must NOT then
    # compound into a step to stage-2 (the historical bug). Per ADR-0004 §2 `review`
    # is the pipeline-entry trigger; a no-row advance performs that same one-time
    # entry. The next advance then moves 1 -> 2 normally.
    active = await _active_stage(session, application_id=app.id, lock=True)
    if active is None:
        return await _materialize_first_stage(
            session,
            app=app,
            principal=principal,
            idempotency_key=idempotency_key,
            ctx=ctx,
            locale=locale,
            emit_trigger=emit_trigger,
        )

    current = await _load_stage(session, stage_id=active.stage_id)
    assert current is not None
    stages = await _template_stages(session, template_id=current.template_id)
    max_order = max(s.sort_order for s in stages)

    # required_action gating (ADR-0005 §3 + ADR-0006 §2). ``manual`` is the
    # trivial-allow path (no query); ``scorecard`` / ``score_threshold`` consult the
    # assignee-aware advance gate and raise the precise 409 — ``scorecard_required``
    # (count not met) or ``score_below_threshold`` (count met but avg below the
    # stage threshold); any unknown action stays fail-closed (unchanged ADR-0004).
    if current.required_action == pipeline.ACTION_MANUAL:
        pass
    elif current.required_action in (
        scorecard.ACTION_SCORECARD,
        interview.ACTION_SCORE_THRESHOLD,
    ):
        from app.modules.recruitment.application import scorecard_service

        gate = await scorecard_service.evaluate_advance_gate(
            session, application_id=app.id, stage=current
        )
        if not gate.allowed:
            if gate.reason == "score_below_threshold":
                raise ScoreBelowThresholdError(
                    avg_overall=gate.avg_overall, threshold=gate.threshold
                )
            raise ScorecardRequiredError(submitted=gate.submitted, required=gate.required)
    else:
        raise IllegalApplicationTransitionError(event=_ADVANCE)
    if not pipeline.can_advance(current.sort_order, max_order):
        raise IllegalApplicationTransitionError(event=_ADVANCE)

    next_stage = min(
        (s for s in stages if s.sort_order > current.sort_order),
        key=lambda s: s.sort_order,
    )

    # One transaction: close current (PASSED), append next ACTIVE, bump version.
    active.status = pipeline.STAGE_PASSED
    active.exit_kind = pipeline.EXIT_ADVANCED
    active.exited_at = _shared.now()
    new_row = CandidateStage(
        application_id=app.id,
        stage_id=next_stage.id,
        status=pipeline.STAGE_ACTIVE,
        entered_at=_shared.now(),
        entered_by=principal.user_id,
        idempotency_key=idempotency_key,
    )
    session.add(new_row)
    app.last_status_at = _shared.now()
    app.version += 1
    await session.flush()

    await write_audit(
        session,
        action="application.stage_advanced",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        after={
            "from_stage": str(current.id),
            "from_order": current.sort_order,
            "to_stage": str(next_stage.id),
            "to_order": next_stage.sort_order,
        },
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.STAGE_ADVANCED,
        actor_id=principal.user_id,
        metadata={"to_stage_name": next_stage.name},
    )

    # Per-stage neutral student notification — silent when the target stage is not
    # candidate-visible (ADR-0004 §4). The coded move is NEVER sent to the student.
    if next_stage.candidate_visible:
        await decision_service._notify_student(
            session,
            app=app,
            template_key="application.stage_advanced",
            notif_type="recruitment.application_stage_advanced",
            dedupe_key=f"application.stage_advanced:{new_row.id}",
            feed_action_url=f"/student/applications/{app.id}?move={new_row.id}",
        )

    await session.commit()
    await session.refresh(app)
    if emit_trigger:
        await _emit_stage_changed(
            session, app=app, from_stage=current, to_stage=next_stage, stage_row_id=new_row.id
        )
    return await _projection(session, app=app, principal=principal, locale=locale)


# --------------------------------------------------------------------------- #
# /rollback                                                                    #
# --------------------------------------------------------------------------- #


async def rollback_application_stage(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    target_stage_id: uuid.UUID,
    reason: str,
    version: int | None = None,
    idempotency_key: str | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    """Move the active stage row back to a STRICTLY prior stage of the template."""

    from app.modules.recruitment.application import decision_service

    # Defensive: the Pydantic schema enforces min-len (422 at the HTTP boundary);
    # this guards any non-HTTP caller. Reason is partner-internal (never sent).
    clean_reason = (reason or "").strip()
    if len(clean_reason) < pipeline.ROLLBACK_REASON_MIN_LEN:
        raise InvalidApplicationFieldError(field="reason")

    app = await decision_service._load_partner_application(
        session, principal=principal, application_id=application_id
    )

    if idempotency_key:
        prior = await _stage_by_idempotency_key(session, application_id=app.id, key=idempotency_key)
        if prior is not None:
            return await _projection(session, app=app, principal=principal, locale=locale)

    if version is not None and version != app.version:
        raise ApplicationVersionConflictError()

    if app.status != lifecycle.UNDER_REVIEW:
        raise IllegalApplicationTransitionError(event=_ROLLBACK)

    await ensure_pipeline_entry(session, app=app, principal=principal)
    active = await _active_stage(session, application_id=app.id, lock=True)
    if active is None:
        raise IllegalApplicationTransitionError(event=_ROLLBACK)

    current = await _load_stage(session, stage_id=active.stage_id)
    assert current is not None
    target = await _load_stage(session, stage_id=target_stage_id)
    # Target must exist, belong to the SAME template, and be a strictly prior stage.
    if (
        target is None
        or target.template_id != current.template_id
        or not pipeline.can_rollback(target.sort_order, current.sort_order)
    ):
        raise IllegalApplicationTransitionError(event=_ROLLBACK)

    # Max 3 rollbacks per application; the 4th is blocked (admin-approval deferred).
    if pipeline.rollback_limit_reached(await _rollback_count(session, application_id=app.id)):
        raise RollbackLimitReachedError()

    # One transaction: close current (ROLLED_BACK), append target ACTIVE, bump.
    active.status = pipeline.STAGE_ROLLED_BACK
    active.exit_kind = pipeline.EXIT_ROLLED_BACK
    active.exited_at = _shared.now()
    active.reason = clean_reason
    new_row = CandidateStage(
        application_id=app.id,
        stage_id=target.id,
        status=pipeline.STAGE_ACTIVE,
        entered_at=_shared.now(),
        entered_by=principal.user_id,
        idempotency_key=idempotency_key,
        # Partner-internal: why the candidate is back in re-review (never sent).
        reason=clean_reason,
    )
    session.add(new_row)
    app.last_status_at = _shared.now()
    app.version += 1
    await session.flush()

    await write_audit(
        session,
        action="application.stage_rolled_back",
        resource_type="application",
        resource_id=app.id,
        context=_shared.audit_ctx(principal, ctx),
        # Reason lives in audit metadata only — never in the student notification.
        after={
            "from_stage": str(current.id),
            "from_order": current.sort_order,
            "to_stage": str(target.id),
            "to_order": target.sort_order,
            "reason": clean_reason,
        },
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.STAGE_ROLLED_BACK,
        actor_id=principal.user_id,
        metadata={"to_stage_name": target.name, "reason": clean_reason},
    )

    # Neutral re-review notification (always — the rollback reason is withheld).
    await decision_service._notify_student(
        session,
        app=app,
        template_key="application.under_rereview",
        notif_type="recruitment.application_under_rereview",
        dedupe_key=f"application.under_rereview:{new_row.id}",
        feed_action_url=f"/student/applications/{app.id}?move={new_row.id}",
    )

    await session.commit()
    await session.refresh(app)
    return await _projection(session, app=app, principal=principal, locale=locale)
