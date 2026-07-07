"""Partner application decision-status machine (Phase 1.5 subset).

Two partner-driven decisions on an application:

- :func:`review_application` — ``submitted -> under_review`` (idempotent).
- :func:`reject_application` — ``{submitted, under_review} -> rejected`` with a
  coded, partner-only ``rejection_reason`` (+ optional internal ``note``).

The full configurable stage engine (``docs/BUSINESS_LOGIC.md`` §3, ``/advance`` /
``/rollback``) stays Phase 2. RBAC + tenant isolation are enforced HERE, not in the
router, using the SAME org-membership gate as ``reveal_service.request_reveal``: a
cross-org or non-partner caller is indistinguishable from a missing resource
(``404``, never ``403``), so applications are not enumerable.

Privacy invariants (``docs/SECURITY_PRIVACY.md`` / ``docs/API_CONTRACTS.md``):

- A status change NEVER exposes the student's identity to the partner and never
  bypasses the anonymous-reveal handshake.
- The student notification + the student application projection carry ONLY the
  localized status label — never the coded ``rejection_reason`` or the partner's
  ``rejection_note``. Those stay org-internal (partner/owner projection only).

Each transition bumps the optimistic ``version``, writes an audit row (the reason
code lives in audit metadata, not the user response), and — in the same
transaction — enqueues the outbox email AND inserts the in-app feed row, mirroring
``reveal_service`` / ``apply_service``. The idempotent no-op path short-circuits
BEFORE any notification, so a double-review / double-reject never duplicates.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.application import ingestion_service as analytics
from app.modules.auth.application.context import RequestContext
from app.modules.notifications.application import feed_service, message_catalog
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.application import job_read_facade
from app.modules.recruitment.application import _shared
from app.modules.recruitment.application.errors import (
    ApplicationVersionConflictError,
    IllegalApplicationTransitionError,
    ScoreBelowThresholdError,
    ScorecardRequiredError,
)
from app.modules.recruitment.domain import lifecycle, timeline
from app.modules.recruitment.domain.models import Application
from app.modules.users.application import user_service
from app.shared.audit import write_audit
from app.shared.exceptions import ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

_RESOURCE = _shared.RESOURCE


async def _load_partner_application(
    session: AsyncSession, *, principal: Principal, application_id: uuid.UUID
) -> Application:
    """Load an application the caller may act on as a partner of its owning org.

    Mirrors ``reveal_service.request_reveal``: a cross-org or non-partner caller is
    indistinguishable from missing (``404``). Row is locked for the read-modify-write.
    """

    app = await _shared.load_application(
        session, application_id=application_id, lock=True
    )
    if not principal.is_superadmin and (
        principal.org_id is None or principal.org_id != app.org_id
    ):
        raise ResourceNotFoundError()
    permission_checker.require(principal, _RESOURCE, "read", resource_org_id=app.org_id)
    return app


async def _partner_projection(
    session: AsyncSession, *, app: Application, principal: Principal, locale: str
) -> dict:
    """Build the partner/owner projection (includes reason/note/last_status_at).

    Identity stays redacted until the reveal handshake is accepted — a decision
    never reveals the student. Reuses the apply_service partner view so the
    anonymity rules are applied in exactly one place.
    """

    from app.modules.recruitment.application import apply_service

    return await apply_service._partner_view(
        session, app=app, principal=principal, locale=locale
    )


async def _resolve_student_locale(
    session: AsyncSession, *, applicant_id: uuid.UUID, student
) -> str:
    pref = getattr(student, "preferred_language", None) if student else None
    return message_catalog.normalize_locale(pref)


async def _job_title(session: AsyncSession, *, job_id: uuid.UUID) -> str | None:
    return await job_read_facade.get_job_title(session, job_id)


async def _notify_student(
    session: AsyncSession,
    *,
    app: Application,
    template_key: str,
    notif_type: str,
    dedupe_key: str | None = None,
    feed_action_url: str | None = None,
) -> None:
    """Enqueue the outbox email AND the in-app feed row, in the caller's txn.

    Neutral copy only: the catalog/template entries carry the localized status
    message — never the ``rejection_reason`` code or the partner ``rejection_note``.
    Locale follows the APPLICANT's own preference.

    ``dedupe_key`` / ``feed_action_url`` default to the per-application keys used by
    the one-shot review/reject decisions. Repeatable moves (stage advance/rollback)
    pass per-move keys so each genuine move notifies once while an at-least-once
    retry of the SAME move still dedupes.
    """

    student = await user_service.get_by_id(session, app.applicant_id)
    if student is None:
        return
    locale = await _resolve_student_locale(
        session, applicant_id=app.applicant_id, student=student
    )
    job_title = await _job_title(session, job_id=app.job_id)
    await enqueue_notification(
        session,
        recipient_id=app.applicant_id,
        template_key=template_key,
        channel="email",
        locale=locale,
        variables={
            "email": student.email,
            "name": student.full_name or "",
            "job_title": job_title or "",
        },
        dedupe_key=dedupe_key or f"{template_key}:{app.id}",
    )
    # In-app feed row (resolves the applicant's locale on its own; action_url
    # dedupe keeps a retried write from duplicating the row).
    await feed_service.create_in_app(
        session,
        recipient_id=app.applicant_id,
        notif_type=notif_type,
        action_url=feed_action_url or f"/student/applications/{app.id}",
        variables={"job_title": job_title or ""},
        locale=locale,
    )


# --------------------------------------------------------------------------- #
# Review: submitted -> under_review                                           #
# --------------------------------------------------------------------------- #


async def review_application(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    app = await _load_partner_application(
        session, principal=principal, application_id=application_id
    )
    if version is not None and version != app.version:
        raise ApplicationVersionConflictError()

    # Review is the pipeline-entry trigger (ADR-0004 §2): materialize the first
    # candidate_stages row at sort_order=1 of the org's default template. Lazy
    # import avoids a stage_service <-> decision_service cycle.
    from app.modules.recruitment.application import stage_service

    # Idempotent: already under_review -> no-op, no duplicate notification. The
    # no-op path STILL ensures the stage row exists (covers an application that
    # reached under_review before the stage engine shipped).
    if app.status == lifecycle.UNDER_REVIEW:
        created = await stage_service.ensure_pipeline_entry(
            session, app=app, principal=principal
        )
        if created:
            await session.commit()
            await session.refresh(app)
        return await _partner_projection(session, app=app, principal=principal, locale=locale)
    if not lifecycle.can_decision_transition(lifecycle.REVIEW, app.status):
        raise IllegalApplicationTransitionError(event=lifecycle.REVIEW)

    app.status = lifecycle.decision_target(lifecycle.REVIEW)
    app.last_status_at = _shared.now()
    app.version += 1
    await session.flush()

    await stage_service.ensure_pipeline_entry(session, app=app, principal=principal)

    await write_audit(
        session, action="application.reviewed", resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        after={"status": app.status},
    )
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.UNDER_REVIEW,
        actor_id=principal.user_id,
    )
    await analytics.record_event_safe(
        session,
        event_type="application.status_changed",
        aggregate_type="application",
        aggregate_id=app.id,
        actor_id=principal.user_id,
        actor_type="partner",
        properties={"to_status": app.status},
    )
    await _notify_student(
        session,
        app=app,
        template_key="application.under_review",
        notif_type="recruitment.application_under_review",
    )

    await session.commit()
    await session.refresh(app)
    return await _partner_projection(session, app=app, principal=principal, locale=locale)


# --------------------------------------------------------------------------- #
# Reject: {submitted, under_review} -> rejected                               #
# --------------------------------------------------------------------------- #


async def reject_application(
    session: AsyncSession,
    *,
    principal: Principal,
    application_id: uuid.UUID,
    reason: str,
    note: str | None = None,
    version: int | None = None,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    app = await _load_partner_application(
        session, principal=principal, application_id=application_id
    )
    if version is not None and version != app.version:
        raise ApplicationVersionConflictError()

    # Defensive: the Pydantic schema already enforces the coded enum (422); this
    # guards any non-HTTP caller. Never trust a raw code through to the DB.
    if reason not in lifecycle.REJECTION_REASONS:
        raise IllegalApplicationTransitionError(event=lifecycle.REJECT)

    # Idempotent: already rejected -> no-op, no duplicate notification. Keep the
    # original reason/note (do not overwrite a prior decision on replay).
    if app.status == lifecycle.REJECTED:
        return await _partner_projection(session, app=app, principal=principal, locale=locale)
    if not lifecycle.can_decision_transition(lifecycle.REJECT, app.status):
        raise IllegalApplicationTransitionError(event=lifecycle.REJECT)

    app.status = lifecycle.decision_target(lifecycle.REJECT)
    app.rejection_reason = reason
    app.rejection_note = (note or None) and note.strip() or None
    app.last_status_at = _shared.now()
    app.version += 1
    await session.flush()

    # Reject is the cross-cutting terminal exit (ADR-0004 §2): close the open
    # candidate_stages row (status REJECTED) without creating a new stage row. A
    # no-op when no stage row exists (e.g. rejected straight from ``submitted``).
    from app.modules.recruitment.application import stage_service

    await stage_service.close_open_stage_on_reject(session, app=app)

    await write_audit(
        session, action="application.rejected", resource_type="application",
        resource_id=app.id, context=_shared.audit_ctx(principal, ctx),
        # Reason lives in audit metadata only — NOT in the user-facing response.
        after={"status": app.status, "rejection_reason": reason},
    )
    # The coded reason/note live in the timeline row's metadata for the partner
    # audit trail, but the student projection NEVER reads ``metadata`` for a
    # ``rejected`` event — only the neutral stored ``label`` (docs/DATA_MODEL §32).
    await timeline.record_timeline_event(
        session,
        application_id=app.id,
        event_type=timeline.REJECTED,
        actor_id=principal.user_id,
        metadata={"rejection_reason": reason, "rejection_note": app.rejection_note},
    )
    await _notify_student(
        session,
        app=app,
        template_key="application.rejected",
        notif_type="recruitment.application_rejected",
    )
    await analytics.record_event_safe(
        session,
        event_type="application.status_changed",
        aggregate_type="application",
        aggregate_id=app.id,
        actor_id=principal.user_id,
        actor_type="partner",
        properties={"to_status": app.status},
    )

    await session.commit()
    await session.refresh(app)
    return await _partner_projection(session, app=app, principal=principal, locale=locale)


# --------------------------------------------------------------------------- #
# Bulk decisions: bulk_review / bulk_reject (partner ATS convenience)         #
# --------------------------------------------------------------------------- #


async def bulk_review_applications(
    session: AsyncSession,
    *,
    principal: Principal,
    application_ids: list[uuid.UUID],
    ctx: RequestContext,
) -> dict:
    """Move up to 100 ``submitted`` applications to ``under_review`` (idempotent).

    Each application is processed independently so a single stale / cross-org
    application does not abort the whole batch. Returns ``{reviewed, skipped,
    errors}`` counts — no individual error detail exposed.
    """
    reviewed = 0
    skipped = 0
    errors = 0
    for app_id in application_ids:
        try:
            await review_application(
                session, principal=principal, application_id=app_id, ctx=ctx
            )
            reviewed += 1
        except IllegalApplicationTransitionError:
            skipped += 1
        except Exception:
            errors += 1
    return {"reviewed": reviewed, "skipped": skipped, "errors": errors}


async def bulk_reject_applications(
    session: AsyncSession,
    *,
    principal: Principal,
    application_ids: list[uuid.UUID],
    reason: str,
    note: str | None,
    ctx: RequestContext,
) -> dict:
    """Reject up to 100 applications in one call (idempotent per item).

    Each application is processed independently so a single illegal transition
    (e.g. already hired) does not abort the whole batch. Already-rejected items
    are counted as ``skipped``.
    """
    rejected = 0
    skipped = 0
    errors = 0
    for app_id in application_ids:
        try:
            await reject_application(
                session,
                principal=principal,
                application_id=app_id,
                reason=reason,
                note=note,
                ctx=ctx,
            )
            rejected += 1
        except IllegalApplicationTransitionError:
            skipped += 1
        except Exception:
            errors += 1
    return {"rejected": rejected, "skipped": skipped, "errors": errors}


async def bulk_advance_applications(
    session: AsyncSession,
    *,
    principal: Principal,
    application_ids: list[uuid.UUID],
    ctx: RequestContext,
    idempotency_key: str | None = None,
) -> dict:
    """Advance up to 100 candidates to their next pipeline stage in one call.

    Each application runs through the SAME gated per-application transaction as
    ``stage_service.advance_application_stage`` (``docs/BUSINESS_LOGIC.md`` §3.6) so
    RBAC (``applications:read`` + org match, 404-not-403), the scorecard /
    score-threshold advance gate, the optimistic version bump, the audit row, and
    the neutral student notification behave EXACTLY as the single-advance endpoint.
    The gate is never bypassed — a candidate whose stage gate is unmet is reported
    as ``blocked``, not force-advanced. Per-item outcomes:

    - ``advanced`` — moved to the next stage.
    - ``blocked``  — an unmet ``scorecard`` / ``score_threshold`` gate on the
      current stage (carries the safe ``{reason, submitted/required}`` or
      ``{reason, avg_overall/threshold}`` — never scorecard content).
    - ``skipped``  — not actionable (not ``under_review``, already at the last
      stage, cross-org, or missing).
    - ``error``    — an unexpected failure on that one item; the batch continues.

    The ``results`` list lets the board show "3/10 couldn't advance" with reasons.
    When a batch ``idempotency_key`` is supplied, each item advances under a derived
    per-application key so an at-least-once retry of the whole batch does not
    double-advance items that already moved (advance is NOT status-idempotent, so
    this matters more than it does for bulk review/reject).
    """

    from app.modules.recruitment.application import stage_service

    advanced = 0
    blocked = 0
    skipped = 0
    errors = 0
    results: list[dict] = []
    for app_id in application_ids:
        item_key = f"{idempotency_key}:{app_id}" if idempotency_key else None
        try:
            await stage_service.advance_application_stage(
                session,
                principal=principal,
                application_id=app_id,
                idempotency_key=item_key,
                ctx=ctx,
            )
            advanced += 1
            results.append({"application_id": str(app_id), "outcome": "advanced"})
        except ScorecardRequiredError as exc:
            blocked += 1
            results.append(
                {
                    "application_id": str(app_id),
                    "outcome": "blocked",
                    "reason": exc.details.get("reason"),
                    "submitted": exc.details.get("submitted"),
                    "required": exc.details.get("required"),
                }
            )
        except ScoreBelowThresholdError as exc:
            blocked += 1
            results.append(
                {
                    "application_id": str(app_id),
                    "outcome": "blocked",
                    "reason": exc.details.get("reason"),
                    "avg_overall": exc.details.get("avg_overall"),
                    "threshold": exc.details.get("threshold"),
                }
            )
        except (IllegalApplicationTransitionError, ApplicationVersionConflictError):
            skipped += 1
            results.append(
                {
                    "application_id": str(app_id),
                    "outcome": "skipped",
                    "reason": "not_advanceable",
                }
            )
        except ResourceNotFoundError:
            skipped += 1
            results.append(
                {
                    "application_id": str(app_id),
                    "outcome": "skipped",
                    "reason": "not_found",
                }
            )
        except Exception:  # noqa: BLE001
            errors += 1
            results.append({"application_id": str(app_id), "outcome": "error"})
    return {
        "advanced": advanced,
        "blocked": blocked,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }
