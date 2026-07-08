"""Discovery service tests (spec §3/§8 — the privacy + idempotency core).

Covers, on the SQLite unit path (privacy/idempotency enforced in the service layer):

- the privacy allowlist: forbidden PII/sensitive/3p-ad-id keys are stripped and
  NEVER reach the DB; only allowlisted coarse keys survive a merge; values clamped.
- session get-or-create from a cookie id (refresh vs new) + user linkage on login.
- coarse-tag merge keeps only allowlisted keys, de-dupes, and caps.
- opt-out/reset clears stored signals and writes a metadata-only audit row.
- record_event idempotency (same key → exactly one row).
- placement_id retained ONLY for sponsored surfaces; dropped on organic.
- scope resolution: anonymous vs session vs user.
- the cleanup sweep prunes expired sessions + old events via the scheduler tick,
  idempotently.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.modules.automation.scheduler import runner
from app.modules.discovery.application import (
    cleanup_service,
    event_service,
    session_service,
)
from app.modules.discovery.domain import allowlist
from app.modules.discovery.domain.models import DiscoveryEvent, DiscoverySession
from app.shared.models import AuditLog
from app.shared.permissions import GUEST, Principal
from sqlalchemy import func, select

from tests.auth_utils import CTX

# --------------------------------------------------------------------------- #
# Allowlist (pure)                                                            #
# --------------------------------------------------------------------------- #


def test_sanitize_strips_forbidden_and_unknown_keys() -> None:
    raw = {
        # forbidden PII / sensitive / 3p-ad-id (every one must be stripped)
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+84900000000",
        "ip": "203.0.113.7",
        "gps": "21.0,105.8",
        "latitude": "21.0",
        "cv_text": "John Candidate, FastAPI, PostgreSQL...",
        "ethnicity": "x",
        "religion": "y",
        "gaid": "ad-id-123",
        "fbclid": "tracking",
        "random_unknown": "z",
        # allowlisted (must survive)
        "categories": ["Data Analyst", "data analyst", "Finance"],
        "industries": ["fintech"],
        "search_terms": ["data analyst intern"],
        "work_mode": "remote",
        "city": "Hanoi",
        "device_type": "mobile",
    }
    clean = allowlist.sanitize_coarse_tags(raw)

    assert set(clean) <= allowlist.ALLOWED_COARSE_TAG_KEYS
    for forbidden in allowlist.FORBIDDEN_COARSE_TAG_KEYS:
        assert forbidden not in clean
    assert "random_unknown" not in clean
    # de-dupe + lowercase
    assert clean["categories"] == ["data analyst", "finance"]
    assert clean["work_mode"] == "remote"
    assert clean["device_type"] == "mobile"
    assert clean["city"] == "hanoi"


def test_sanitize_drops_out_of_vocab_scalars() -> None:
    clean = allowlist.sanitize_coarse_tags(
        {"work_mode": "telepathy", "device_type": "hologram"}
    )
    assert clean == {}


def test_merge_dedupes_caps_and_stays_allowlisted() -> None:
    existing = {"categories": ["python"], "name": "leak"}  # name shouldn't persist
    incoming = {"categories": ["python", "go"], "email": "x@y.z"}
    merged = allowlist.merge_coarse_tags(existing, incoming)
    assert merged == {"categories": ["python", "go"]}
    assert "name" not in merged and "email" not in merged

    many = {"categories": [f"c{i}" for i in range(40)]}
    capped = allowlist.merge_coarse_tags({}, many)
    assert len(capped["categories"]) <= 20


# --------------------------------------------------------------------------- #
# Session get-or-create + signal merge + opt-out/reset                        #
# --------------------------------------------------------------------------- #


async def test_get_or_create_new_then_refresh(db_session) -> None:
    s1 = await session_service.get_or_create(db_session, cookie_id=None, locale="vi")
    await db_session.commit()
    assert s1.locale == "vi"
    assert s1.coarse_tags == {}

    # Same cookie id → SAME row refreshed (not a new one).
    s2 = await session_service.get_or_create(db_session, cookie_id=str(s1.id))
    await db_session.commit()
    assert s2.id == s1.id
    count = (
        await db_session.execute(select(func.count()).select_from(DiscoverySession))
    ).scalar_one()
    assert count == 1

    # Garbage / unknown cookie id → brand-new session.
    s3 = await session_service.get_or_create(db_session, cookie_id="not-a-uuid")
    await db_session.commit()
    assert s3.id != s1.id


async def test_record_signal_only_allowlisted_persisted(db_session) -> None:
    s = await session_service.get_or_create(db_session, cookie_id=None)
    await session_service.record_signal(
        db_session,
        s,
        tags={
            "categories": ["Data Analyst"],
            "email": "leak@example.com",
            "gps": "21.0,105.8",
            "cv_text": "raw cv body",
        },
    )
    await db_session.commit()
    await db_session.refresh(s)
    assert s.coarse_tags == {"categories": ["data analyst"]}
    assert "email" not in s.coarse_tags
    assert "gps" not in s.coarse_tags
    assert "cv_text" not in s.coarse_tags


async def test_user_linked_on_login(db_session) -> None:
    s = await session_service.get_or_create(db_session, cookie_id=None)
    await db_session.commit()
    assert s.user_id is None
    user_id = uuid.uuid4()
    principal = Principal(user_id=user_id, persona="student")
    again = await session_service.get_or_create(
        db_session, cookie_id=str(s.id), principal=principal
    )
    await db_session.commit()
    assert again.id == s.id
    assert again.user_id == user_id


async def test_reset_clears_signals_and_opts_out_with_audit(db_session) -> None:
    s = await session_service.get_or_create(db_session, cookie_id=None)
    await session_service.record_signal(db_session, s, tags={"categories": ["python"]})
    await db_session.commit()

    cleared = await session_service.reset(
        db_session, cookie_id=str(s.id), opt_out=True, ctx=CTX
    )
    assert cleared is not None
    assert cleared.coarse_tags == {}
    assert cleared.opt_out is True

    # A metadata-only audit row exists and carries NO coarse tags / PII.
    audit = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "discovery.session_reset")
        )
    ).scalar_one()
    assert audit.resource_id == s.id
    assert audit.after_snapshot == {"opt_out": True, "signals_cleared": True}
    assert audit.ip_hash is not None and audit.ip_hash != CTX.ip  # hashed, not raw

    # An opted-out session refuses further signals.
    await session_service.record_signal(db_session, cleared, tags={"categories": ["go"]})
    await db_session.commit()
    await db_session.refresh(cleared)
    assert cleared.coarse_tags == {}


# --------------------------------------------------------------------------- #
# Event sink: idempotency, placement gating, scope                            #
# --------------------------------------------------------------------------- #


async def test_record_event_is_idempotent(db_session) -> None:
    s = await session_service.get_or_create(db_session, cookie_id=None)
    key = uuid.uuid4().hex
    target = uuid.uuid4()
    e1 = await event_service.record_event(
        db_session, principal=GUEST, discovery_session=s,
        event_type="impression", source_surface="homepage_recommended",
        target_type="job", target_id=target, idempotency_key=key,
    )
    e2 = await event_service.record_event(
        db_session, principal=GUEST, discovery_session=s,
        event_type="impression", source_surface="homepage_recommended",
        target_type="job", target_id=target, idempotency_key=key,
    )
    await db_session.commit()
    assert e1.id == e2.id
    count = (
        await db_session.execute(select(func.count()).select_from(DiscoveryEvent))
    ).scalar_one()
    assert count == 1


async def test_placement_id_only_kept_for_sponsored_surface(db_session) -> None:
    s = await session_service.get_or_create(db_session, cookie_id=None)
    placement = uuid.uuid4()

    organic = await event_service.record_event(
        db_session, principal=GUEST, discovery_session=s,
        event_type="impression", source_surface="homepage_recommended",
        target_type="job", target_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4().hex, placement_id=placement,
    )
    sponsored = await event_service.record_event(
        db_session, principal=GUEST, discovery_session=s,
        event_type="impression", source_surface="homepage_sponsored",
        target_type="job", target_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4().hex, placement_id=placement,
    )
    await db_session.commit()
    assert organic.placement_id is None  # organic surface drops the placement ref
    assert sponsored.placement_id == placement


async def test_scope_resolution_anonymous_session_user(db_session) -> None:
    s = await session_service.get_or_create(db_session, cookie_id=None)

    # session scope (guest with a live session)
    sess_evt = await event_service.record_event(
        db_session, principal=GUEST, discovery_session=s,
        event_type="view", source_surface="job_detail", target_type="job",
        target_id=uuid.uuid4(), idempotency_key=uuid.uuid4().hex,
    )
    # user scope (authenticated)
    principal = Principal(user_id=uuid.uuid4(), persona="student")
    user_evt = await event_service.record_event(
        db_session, principal=principal, discovery_session=s,
        event_type="view", source_surface="job_detail", target_type="job",
        target_id=uuid.uuid4(), idempotency_key=uuid.uuid4().hex,
    )
    # anonymous scope (no session at all)
    anon_evt = await event_service.record_event(
        db_session, principal=GUEST, discovery_session=None,
        event_type="view", source_surface="job_detail", target_type="job",
        target_id=uuid.uuid4(), idempotency_key=uuid.uuid4().hex,
    )
    await db_session.commit()

    assert sess_evt.scope == "session" and sess_evt.session_id == s.id
    assert sess_evt.user_id is None
    assert user_evt.scope == "user" and user_evt.user_id == principal.user_id
    assert anon_evt.scope == "anonymous" and anon_evt.session_id is None


async def test_invalid_vocab_rejected(db_session) -> None:
    from app.modules.discovery.application.errors import InvalidDiscoveryEventError

    s = await session_service.get_or_create(db_session, cookie_id=None)
    for bad in (
        {"event_type": "hover"},
        {"source_surface": "totally_unknown_surface"},
        {"target_type": "spaceship"},
    ):
        kwargs = dict(
            event_type="impression", source_surface="homepage_recommended",
            target_type="job",
        )
        kwargs.update(bad)
        try:
            await event_service.record_event(
                db_session, principal=GUEST, discovery_session=s,
                target_id=uuid.uuid4(), idempotency_key=uuid.uuid4().hex, **kwargs,
            )
            raise AssertionError(f"expected rejection for {bad}")
        except InvalidDiscoveryEventError:
            pass


# --------------------------------------------------------------------------- #
# Cleanup sweep via the scheduler tick (idempotent)                           #
# --------------------------------------------------------------------------- #


async def test_cleanup_sweep_prunes_expired_via_tick(db_session) -> None:
    now = datetime.now(tz=UTC)
    # An expired session + a live one.
    expired = DiscoverySession(
        id=uuid.uuid4(), coarse_tags={}, opt_out=False,
        created_at=now - timedelta(days=40), last_seen_at=now - timedelta(days=40),
        expires_at=now - timedelta(days=1),
    )
    live = DiscoverySession(
        id=uuid.uuid4(), coarse_tags={}, opt_out=False,
        created_at=now, last_seen_at=now, expires_at=now + timedelta(days=30),
    )
    # An old event (out of retention) + a fresh one.
    old_evt = DiscoveryEvent(
        id=uuid.uuid4(), event_type="impression", source_surface="search",
        target_type="job", target_id=uuid.uuid4(), scope="anonymous",
        idempotency_key=uuid.uuid4().hex, created_at=now - timedelta(days=120),
    )
    fresh_evt = DiscoveryEvent(
        id=uuid.uuid4(), event_type="impression", source_surface="search",
        target_type="job", target_id=uuid.uuid4(), scope="anonymous",
        idempotency_key=uuid.uuid4().hex, created_at=now,
    )
    db_session.add_all([expired, live, old_evt, fresh_evt])
    await db_session.commit()

    # Drive it through the scheduler tick (proves it runs AS SCHEDULED).
    results = await runner.tick(only=["discovery.session_cleanup"])
    res = results["discovery.session_cleanup"]
    assert res["sessions_pruned"] == 1
    assert res["events_pruned"] == 1

    remaining_sessions = (
        await db_session.execute(select(DiscoverySession.id))
    ).scalars().all()
    remaining_events = (
        await db_session.execute(select(DiscoveryEvent.id))
    ).scalars().all()
    assert remaining_sessions == [live.id]
    assert remaining_events == [fresh_evt.id]

    # Re-tick is a no-op (idempotent).
    again = await cleanup_service.session_cleanup(db_session, now=now)
    assert again == {"sessions_pruned": 0, "events_pruned": 0}
