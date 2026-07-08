"""Scheduled AI job-alert EMAIL digest sweep (WS-15, Task N).

A DAILY digest of newly-matched jobs for each student's active job alerts,
delivered via the notifications **outbox + template renderer** (no synchronous
SMTP). Distinct from the real-time in-app match nudge
(:mod:`opportunities.application.job_alert_dispatch_service`, 30-min cadence):

- **Deterministic matching (free).** Reuses the exact canonical matcher
  (``job_alert_dispatch_service._find_matches`` — same public-visibility predicate
  at the student tier, same keyword/type/location filters) so a student is never
  digested a job they could not discover. Jobs published since the alert's own
  ``last_digest_at`` watermark (or a bounded lookback for never-digested alerts)
  are the candidates.
- **Optional AI summary line (metered).** ONE short, grounded sentence over the
  matched titles, added only when a real provider is enabled AND the student still
  has weekly AI energy. Charged (``job_alert_digest``) once per (alert, window) on
  success; the digest ships deterministically without it otherwise. The AI never
  invents or reorders jobs.
- **Idempotent per (alert, digest-window).** The outbox ``dedupe_key`` keys on the
  alert + the UTC date, so a re-run within the same day never double-sends. The
  ``last_digest_at`` watermark advances after each alert is processed.
- **Respects preferences.** A student who set the ``job_alert`` email category to
  ``off`` is skipped (no email enqueued); the watermark still advances.
- **PII-safe.** Only the student's own alert name + public job titles reach the
  email body; no provider/model/token/cost internals ever leak.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv.llm import generate_note
from app.ai.energy import service as energy_service
from app.ai.energy.constants import FEATURE_JOB_ALERT_DIGEST
from app.ai.gateway.factory import real_provider_active
from app.ai.observability.billable_usage import (
    PERSONA_STUDENT,
    SCOPE_USER,
    UsageContext,
    make_idempotency_key,
    record_billable_usage,
)
from app.ai.prompts.job_alert_digest import v1 as digest_prompt
from app.modules.notifications.application import dispatch_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.opportunities.application import job_alert_dispatch_service
from app.modules.opportunities.domain.models import JobAlert
from app.modules.users.application import user_read_facade
from app.shared.exceptions import AIUnavailableError
from app.shared.permissions import Principal

logger = logging.getLogger(__name__)

# Never-digested alerts look back this far so a brand-new alert's first digest is
# not empty just because it was created after some matching jobs went live.
_LOOKBACK_HOURS = 24
_BATCH_ALERTS = 200
_MAX_DIGEST_ROWS = 8
# Preference category (users.domain.preferences) that gates the email channel.
_PREF_CATEGORY = "job_alert"
_DIGEST_URL = "/student/alerts"


async def sweep_job_alert_digests(
    session: AsyncSession, now: datetime
) -> dict[str, int]:
    """Enqueue an email digest per active alert with new matches. Idempotent."""

    cutoff_default = now - timedelta(hours=_LOOKBACK_HOURS)
    use_jsonb = session.get_bind().dialect.name == "postgresql"

    alerts: list[JobAlert] = list(
        (
            await session.execute(
                select(JobAlert)
                .where(JobAlert.is_active.is_(True))
                .order_by(JobAlert.created_at.asc())
                .limit(_BATCH_ALERTS)
            )
        )
        .scalars()
        .all()
    )
    if not alerts:
        return {
            "alerts_swept": 0,
            "digests_enqueued": 0,
            "skipped_no_match": 0,
            "skipped_pref_off": 0,
            "skipped_dupe": 0,
            "ai_summaries": 0,
        }

    contacts = await user_read_facade.contacts_by_ids(
        session, [a.user_id for a in alerts]
    )

    enqueued = skipped_no_match = skipped_pref = skipped_dupe = ai_summaries = 0

    for alert in alerts:
        cutoff = alert.last_digest_at if alert.last_digest_at is not None else cutoff_default
        matches = await job_alert_dispatch_service._find_matches(
            session, alert=alert, since=cutoff, now=now, use_jsonb=use_jsonb
        )
        # Watermark advances whether or not there were matches / an email was sent,
        # so the next window starts fresh (the dedupe_key is the send-idempotency
        # backstop within a day).
        alert.last_digest_at = now

        if not matches:
            skipped_no_match += 1
            continue

        contact = contacts.get(alert.user_id)
        if contact is None:  # deactivated / deleted recipient
            skipped_no_match += 1
            continue

        # Respect the student's email preference for this category (spec §5): an
        # explicit ``off`` mutes the email; ``None`` means the category default
        # (on) applies.
        email_setting = await user_read_facade.get_notification_email_setting(
            session, user_id=alert.user_id, category=_PREF_CATEGORY
        )
        if email_setting == "off":
            skipped_pref += 1
            continue

        dedupe_key = f"job.alert_digest:{alert.id}:{now.date().isoformat()}"
        if await dispatch_service.dedupe_exists(session, dedupe_key=dedupe_key):
            skipped_dupe += 1
            continue

        locale = _normalize_locale(contact.preferred_language)
        titles = [m["title"] for m in matches[:_MAX_DIGEST_ROWS]]
        job_lines = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))

        # Optional, metered AI summary line — deterministic core ships regardless.
        ai_summary, charged = await _maybe_ai_summary(
            session,
            alert=alert,
            titles=titles,
            locale=locale,
            now=now,
        )
        if charged:
            ai_summaries += 1

        await enqueue_notification(
            session,
            recipient_id=alert.user_id,
            template_key="job.alert_digest",
            channel="email",
            locale=locale,
            variables={
                "name": contact.full_name or "",
                "email": contact.email,
                "alert_name": alert.name,
                "match_count": str(len(titles)),
                "job_lines": job_lines,
                # Empty string when the AI line is off/exhausted/unavailable; the
                # template renders it as a blank prefix line.
                "ai_summary": (f"{ai_summary}\n\n" if ai_summary else ""),
                "url": _DIGEST_URL,
            },
            dedupe_key=dedupe_key,
        )
        enqueued += 1

    await session.commit()
    result = {
        "alerts_swept": len(alerts),
        "digests_enqueued": enqueued,
        "skipped_no_match": skipped_no_match,
        "skipped_pref_off": skipped_pref,
        "skipped_dupe": skipped_dupe,
        "ai_summaries": ai_summaries,
    }
    logger.info("job_alert_digest.sweep", extra=result)
    return result


def _normalize_locale(pref: str | None) -> str:
    return "en" if (pref or "vi").lower().startswith("en") else "vi"


async def _maybe_ai_summary(
    session: AsyncSession,
    *,
    alert: JobAlert,
    titles: list[str],
    locale: str,
    now: datetime,
) -> tuple[str | None, bool]:
    """Return ``(summary_line, charged)`` for the optional AI digest sentence.

    Gated on a real provider being enabled AND the student's own weekly AI energy.
    Best-effort: any failure degrades to ``(None, False)`` so the deterministic
    digest still ships. Charges ``job_alert_digest`` energy exactly once per
    (alert, UTC-day) on a successful, user-visible line.
    """

    if not real_provider_active():
        return None, False

    # Per-student weekly gate; on exhaustion just skip the AI line (no 409, no charge).
    # A synthetic student Principal lets us reuse the canonical energy meter without
    # a request context (the background sweep has no logged-in caller).
    try:
        student = Principal(user_id=alert.user_id, persona=PERSONA_STUDENT)
        snap = await energy_service.snapshot(session, principal=student)
        if snap.blocked:
            return None, False
    except Exception:  # noqa: BLE001 — metering read must never break the sweep
        return None, False

    try:
        text_out = await generate_note(
            task_type="job_alert_digest",
            system_prompt=digest_prompt.system_prompt(locale=locale),
            user_content=digest_prompt.build_user_content(
                alert_name=alert.name, job_titles=titles
            ),
            temperature=0.3,
            max_tokens=80,
        )
    except AIUnavailableError:
        return None, False
    except Exception:  # noqa: BLE001 — advisory enrichment, never break the digest
        logger.warning("job_alert_digest.ai_summary_failed", exc_info=True)
        return None, False

    text_out = (text_out or "").strip()
    if not text_out:
        return None, False

    charged = await _charge_digest_energy(session, alert=alert, now=now)
    return text_out, charged


async def _charge_digest_energy(
    session: AsyncSession, *, alert: JobAlert, now: datetime
) -> bool:
    """Debit one digest-summary credit, idempotent per (alert, UTC-day)."""

    try:
        ctx = UsageContext(
            actor_persona=PERSONA_STUDENT,
            feature_key=FEATURE_JOB_ALERT_DIGEST,
            task_type="job_alert_digest",
            billing_scope=SCOPE_USER,
            actor_user_id=alert.user_id,
            resource_type="job_alert",
            resource_id=alert.id,
            idempotency_key=make_idempotency_key(
                FEATURE_JOB_ALERT_DIGEST, alert.id, now.date().isoformat()
            ),
        )
        await record_billable_usage(
            session,
            ctx=ctx,
            result_status="success",
            base_units=energy_service.charge_units(FEATURE_JOB_ALERT_DIGEST),
        )
        return True
    except Exception:  # noqa: BLE001 — accounting must never break the digest
        logger.warning("job_alert_digest.energy_charge_failed", exc_info=True)
        return False
