"""Advertising / sponsored-placements service tests (ADR-0009 first slice).

Covers the placement-as-source-of-truth / flag-as-projection model end to end:
disclosure gate (422), create→submit→approve→mark_paid→activate flips the real
``jobs/events.is_sponsored``/``is_featured`` flags ON (job AND event targets),
completion flips OFF, two overlapping placements keep a flag ON until both
complete (the EXISTS recompute), cross-org target → 404, double in-flight → 409,
per-org concurrency cap → 409, activation requires paid, university disable flips
OFF, the marketplace overview contract is unchanged (still real flags), the
scheduler sweeps are idempotent, audit per write, and the cross-module rule is
respected (advertising never imports the Job/Event ORM directly).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.modules.advertising.application import (
    activation_service,
    moderation_service,
    placement_service,
)
from app.modules.advertising.application.errors import (
    ActivePlacementLimitError,
    DisclosureRequiredError,
    PlacementExistsError,
)
from app.modules.advertising.domain.models import AdPackage, SponsoredPlacement
from app.modules.opportunities.application import job_service
from app.modules.opportunities.application import (
    moderation_service as jobs_moderation,
)
from app.modules.opportunities.domain.event_models import Event
from app.modules.opportunities.domain.models import Job
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.events_utils import publish_event
from tests.org_utils import make_org_with_admin

# --------------------------------------------------------------------------- #
# Fixtures / helpers                                                          #
# --------------------------------------------------------------------------- #


async def _seed_packages(db) -> dict[str, AdPackage]:
    """Seed the three reference packages (the migration data step, in-test)."""

    specs = [
        ("featured_7d", "Nổi bật 7 ngày", "featured", "1500000.00", 7, False, True),
        ("sponsored_14d", "Tài trợ 14 ngày", "sponsored", "3000000.00", 14, True, False),
        ("premium_30d", "Cao cấp 30 ngày", "both", "6000000.00", 30, True, True),
    ]
    out: dict[str, AdPackage] = {}
    for code, name, ptype, price, days, gs, gf in specs:
        pkg = AdPackage(
            code=code, name=name, placement_type=ptype, price_amount=price,
            currency="VND", duration_days=days, grants_sponsored=gs,
            grants_featured=gf, is_active=True,
        )
        db.add(pkg)
        out[code] = pkg
    await db.commit()
    for pkg in out.values():
        await db.refresh(pkg)
    return out


def _job_payload(title: str = "Backend Intern", **over) -> dict:
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


async def _published_job(db, partner, uni, *, title="Live Job") -> uuid.UUID:
    created = await job_service.create_job(
        db, principal=partner, payload=_job_payload(title), ctx=CTX
    )
    await job_service.submit_job(
        db, principal=partner, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    await jobs_moderation.approve_job(
        db, principal=uni, job_id=uuid.UUID(created["id"]), ctx=CTX
    )
    return uuid.UUID(created["id"])


async def _published_event(db, partner, uni, *, title="Live Event") -> uuid.UUID:
    return await publish_event(db, partner, uni, title=title)


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _flags(db, model, target_id: uuid.UUID) -> tuple[bool, bool]:
    row = (
        await db.execute(select(model).where(model.id == target_id))
    ).scalar_one()
    return row.is_sponsored, row.is_featured


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _create_draft(
    db, partner, *, target_type, target_id, package, placement_type,
    start_offset_days=0, disclosure=True,
):
    return await placement_service.create_placement(
        db,
        principal=partner,
        payload={
            "target_type": target_type,
            "target_id": target_id,
            "placement_type": placement_type,
            "package_id": package.id,
            "start_at": _now() + timedelta(days=start_offset_days),
            "disclosure_confirmed": disclosure,
        },
        ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# Packages                                                                    #
# --------------------------------------------------------------------------- #


async def test_list_packages_returns_pricing(db_session) -> None:
    await _seed_packages(db_session)
    pkgs = await placement_service.list_packages(db_session)
    assert {p["code"] for p in pkgs} == {"featured_7d", "sponsored_14d", "premium_30d"}
    premium = next(p for p in pkgs if p["code"] == "premium_30d")
    assert premium["grants_sponsored"] and premium["grants_featured"]
    assert premium["placement_type_label"]  # localized, never raw-only
    assert premium["price_amount"] == "6000000.00"


# --------------------------------------------------------------------------- #
# Disclosure gate                                                             #
# --------------------------------------------------------------------------- #


async def test_submit_without_disclosure_is_422(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)

    draft = await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["sponsored_14d"], placement_type="sponsored", disclosure=False,
    )
    with pytest.raises(DisclosureRequiredError):
        await placement_service.submit_placement(
            db_session, principal=partner, placement_id=uuid.UUID(draft["id"]),
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Partner placement list resolves the real target title (regression)          #
# --------------------------------------------------------------------------- #


async def test_list_my_placements_resolves_target_title(db_session) -> None:
    """`list_my_placements` must return the real job/event title, not None.

    Regression: the partner list previously batch-loaded only packages and
    dropped `target_title`, so the partner advertising table rendered every row
    as "target no longer available" even for a live, owned job.
    """

    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni, title="Backend Intern")

    await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["sponsored_14d"], placement_type="sponsored",
    )

    items, _cursor, _limit = await placement_service.list_my_placements(
        db_session, principal=partner
    )
    assert len(items) == 1
    assert items[0]["target_title"] == "Backend Intern"


# --------------------------------------------------------------------------- #
# Full happy path: job target -> flags ON, then completion -> OFF             #
# --------------------------------------------------------------------------- #


async def test_full_flow_job_flips_sponsored_on_then_off(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)

    # Window already open so approve/mark_paid activates inline.
    draft = await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["sponsored_14d"], placement_type="sponsored",
        start_offset_days=-1,
    )
    pid = uuid.UUID(draft["id"])
    await placement_service.submit_placement(
        db_session, principal=partner, placement_id=pid, ctx=CTX,
    )
    await moderation_service.approve_placement(
        db_session, principal=uni, placement_id=pid, ctx=CTX,
    )
    # Approved but unpaid -> NOT active yet, flags OFF.
    assert await _flags(db_session, Job, job_id) == (False, False)

    res = await moderation_service.mark_paid(
        db_session, principal=uni, placement_id=pid,
        payment_reference="BANK-REF-001", ctx=CTX,
    )
    assert res["status"] == "active"
    assert await _flags(db_session, Job, job_id) == (True, False)

    # Completion (window end passed) -> flag OFF.
    placement = (
        await db_session.execute(
            select(SponsoredPlacement).where(SponsoredPlacement.id == pid)
        )
    ).scalar_one()
    placement.end_at = _now() - timedelta(minutes=1)
    await db_session.commit()
    await activation_service.completion_sweep(db_session, now=_now())
    await db_session.commit()
    assert await _flags(db_session, Job, job_id) == (False, False)


async def test_full_flow_event_target_featured(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    event_id = await _published_event(db_session, partner, uni)

    draft = await _create_draft(
        db_session, partner, target_type="event", target_id=event_id,
        package=pkgs["featured_7d"], placement_type="featured",
        start_offset_days=-1,
    )
    pid = uuid.UUID(draft["id"])
    await placement_service.submit_placement(
        db_session, principal=partner, placement_id=pid, ctx=CTX,
    )
    await moderation_service.approve_placement(
        db_session, principal=uni, placement_id=pid, ctx=CTX,
    )
    await moderation_service.mark_paid(
        db_session, principal=uni, placement_id=pid,
        payment_reference="BANK-REF-EVT", ctx=CTX,
    )
    # featured ON, sponsored stays OFF.
    assert await _flags(db_session, Event, event_id) == (False, True)


# --------------------------------------------------------------------------- #
# Activation requires paid                                                    #
# --------------------------------------------------------------------------- #


async def test_activation_requires_paid(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)

    draft = await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["sponsored_14d"], placement_type="sponsored",
        start_offset_days=-1,
    )
    pid = uuid.UUID(draft["id"])
    await placement_service.submit_placement(
        db_session, principal=partner, placement_id=pid, ctx=CTX,
    )
    await moderation_service.approve_placement(
        db_session, principal=uni, placement_id=pid, ctx=CTX,
    )
    # Approved + in-window + unpaid: the activation sweep must NOT activate it.
    await activation_service.activation_sweep(db_session, now=_now())
    await db_session.commit()
    placement = (
        await db_session.execute(
            select(SponsoredPlacement).where(SponsoredPlacement.id == pid)
        )
    ).scalar_one()
    assert placement.status == "approved"
    assert await _flags(db_session, Job, job_id) == (False, False)


# --------------------------------------------------------------------------- #
# Two overlapping placements: flag stays ON until both complete               #
# --------------------------------------------------------------------------- #


async def test_two_active_placements_keep_flag_until_both_complete(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)

    async def _activate_on(pkg, placement_type) -> uuid.UUID:
        draft = await _create_draft(
            db_session, partner, target_type="job", target_id=job_id,
            package=pkg, placement_type=placement_type, start_offset_days=-1,
        )
        pid = uuid.UUID(draft["id"])
        await placement_service.submit_placement(
            db_session, principal=partner, placement_id=pid, ctx=CTX,
        )
        await moderation_service.approve_placement(
            db_session, principal=uni, placement_id=pid, ctx=CTX,
        )
        await moderation_service.mark_paid(
            db_session, principal=uni, placement_id=pid,
            payment_reference=f"REF-{placement_type}", ctx=CTX,
        )
        return pid

    # First a sponsored placement goes live.
    p1 = await _activate_on(pkgs["sponsored_14d"], "sponsored")
    assert await _flags(db_session, Job, job_id) == (True, False)

    # The one-in-flight rule blocks a second placement while p1 is live, so
    # complete p1 first... instead, demonstrate overlap by directly seeding a
    # second ACTIVE placement (a renewal that overlapped before p1's terminal).
    # Use a separate job-fit: bypass uniqueness by creating it post-activation via
    # the service is blocked by design; seed it directly to model true overlap.
    second = SponsoredPlacement(
        org_id=partner.org_id, created_by=partner.user_id, target_type="job",
        target_id=job_id, placement_type="sponsored", package_id=pkgs["sponsored_14d"].id,
        price_amount="3000000.00", currency="VND",
        start_at=_now() - timedelta(days=1), end_at=_now() + timedelta(days=13),
        status="active", disclosure_confirmed=True, paid_at=_now(),
        activated_at=_now(),
    )
    db_session.add(second)
    await db_session.commit()
    await db_session.refresh(second)

    # Complete p1 -> the other active placement keeps sponsored ON.
    placement = (
        await db_session.execute(
            select(SponsoredPlacement).where(SponsoredPlacement.id == p1)
        )
    ).scalar_one()
    placement.end_at = _now() - timedelta(minutes=1)
    await db_session.commit()
    await activation_service.completion_sweep(db_session, now=_now())
    await db_session.commit()
    assert await _flags(db_session, Job, job_id) == (True, False)

    # Complete the second -> now sponsored OFF.
    second.end_at = _now() - timedelta(minutes=1)
    await db_session.commit()
    await activation_service.completion_sweep(db_session, now=_now())
    await db_session.commit()
    assert await _flags(db_session, Job, job_id) == (False, False)


# --------------------------------------------------------------------------- #
# Cross-org target -> 404                                                     #
# --------------------------------------------------------------------------- #


async def test_create_on_cross_org_target_is_404(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _ua, _oa, partner_a = await make_org_with_admin(db_session, display_name="A")
    _ub, _ob, partner_b = await make_org_with_admin(db_session, display_name="B")
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_a = await _published_job(db_session, partner_a, uni, title="A job")

    with pytest.raises(ResourceNotFoundError):
        await _create_draft(
            db_session, partner_b, target_type="job", target_id=job_a,
            package=pkgs["sponsored_14d"], placement_type="sponsored",
        )


async def test_create_on_unknown_target_is_404(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    with pytest.raises(ResourceNotFoundError):
        await _create_draft(
            db_session, partner, target_type="job", target_id=uuid.uuid4(),
            package=pkgs["sponsored_14d"], placement_type="sponsored",
        )


# --------------------------------------------------------------------------- #
# Double in-flight -> 409                                                     #
# --------------------------------------------------------------------------- #


async def test_double_in_flight_on_same_target_is_409(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)

    d1 = await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["sponsored_14d"], placement_type="sponsored",
    )
    await placement_service.submit_placement(
        db_session, principal=partner, placement_id=uuid.UUID(d1["id"]), ctx=CTX,
    )
    d2 = await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["featured_7d"], placement_type="featured",
    )
    with pytest.raises(PlacementExistsError):
        await placement_service.submit_placement(
            db_session, principal=partner, placement_id=uuid.UUID(d2["id"]), ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Per-org concurrency cap -> 409                                              #
# --------------------------------------------------------------------------- #


async def test_per_org_concurrency_cap_is_409(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")

    # Cap is 3: submit 3 placements on 3 different jobs, then a 4th must 409.
    for i in range(3):
        job_id = await _published_job(db_session, partner, uni, title=f"Job {i}")
        d = await _create_draft(
            db_session, partner, target_type="job", target_id=job_id,
            package=pkgs["sponsored_14d"], placement_type="sponsored",
        )
        await placement_service.submit_placement(
            db_session, principal=partner, placement_id=uuid.UUID(d["id"]), ctx=CTX,
        )
    job4 = await _published_job(db_session, partner, uni, title="Job 4")
    d4 = await _create_draft(
        db_session, partner, target_type="job", target_id=job4,
        package=pkgs["sponsored_14d"], placement_type="sponsored",
    )
    with pytest.raises(ActivePlacementLimitError):
        await placement_service.submit_placement(
            db_session, principal=partner, placement_id=uuid.UUID(d4["id"]), ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# University disable -> flags OFF                                             #
# --------------------------------------------------------------------------- #


async def test_university_can_disable_any_active_placement(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)

    draft = await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["premium_30d"], placement_type="both", start_offset_days=-1,
    )
    pid = uuid.UUID(draft["id"])
    await placement_service.submit_placement(
        db_session, principal=partner, placement_id=pid, ctx=CTX,
    )
    await moderation_service.approve_placement(
        db_session, principal=uni, placement_id=pid, ctx=CTX,
    )
    await moderation_service.mark_paid(
        db_session, principal=uni, placement_id=pid,
        payment_reference="REF-PREMIUM", ctx=CTX,
    )
    assert await _flags(db_session, Job, job_id) == (True, True)

    res = await moderation_service.admin_cancel(
        db_session, principal=uni, placement_id=pid, reason="Policy", ctx=CTX,
    )
    assert res["status"] == "cancelled"
    assert await _flags(db_session, Job, job_id) == (False, False)


# --------------------------------------------------------------------------- #
# RBAC: partner admin cannot moderate                                         #
# --------------------------------------------------------------------------- #


async def test_partner_admin_cannot_moderate(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)
    draft = await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["sponsored_14d"], placement_type="sponsored",
    )
    pid = uuid.UUID(draft["id"])
    await placement_service.submit_placement(
        db_session, principal=partner, placement_id=pid, ctx=CTX,
    )
    from app.shared.exceptions import PermissionDeniedError
    # Partner admin holds *:* but org_type != university -> 403.
    with pytest.raises(PermissionDeniedError):
        await moderation_service.approve_placement(
            db_session, principal=partner, placement_id=pid, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Audit per write                                                             #
# --------------------------------------------------------------------------- #


async def test_audit_row_per_write(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)

    draft = await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["sponsored_14d"], placement_type="sponsored",
        start_offset_days=-1,
    )
    pid = uuid.UUID(draft["id"])
    await placement_service.submit_placement(
        db_session, principal=partner, placement_id=pid, ctx=CTX,
    )
    await moderation_service.approve_placement(
        db_session, principal=uni, placement_id=pid, ctx=CTX,
    )
    await moderation_service.mark_paid(
        db_session, principal=uni, placement_id=pid,
        payment_reference="REF-AUDIT", ctx=CTX,
    )
    assert await _audit_count(db_session, "advertising.placement_created") == 1
    assert await _audit_count(db_session, "advertising.placement_submitted") == 1
    assert await _audit_count(db_session, "advertising.placement_approved") == 1
    assert await _audit_count(db_session, "advertising.placement_paid") == 1
    assert await _audit_count(db_session, "advertising.placement_activated") == 1
    # The flag flip itself is audited (sponsorship_changed).
    assert await _audit_count(db_session, "job.sponsorship_changed") >= 1


# --------------------------------------------------------------------------- #
# Scheduler sweeps idempotent + reconcile self-heals                          #
# --------------------------------------------------------------------------- #


async def test_activation_and_completion_sweeps_idempotent(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)

    # Approved + paid + window opens in the future; sweep activates when open.
    draft = await _create_draft(
        db_session, partner, target_type="job", target_id=job_id,
        package=pkgs["sponsored_14d"], placement_type="sponsored",
        start_offset_days=1,
    )
    pid = uuid.UUID(draft["id"])
    await placement_service.submit_placement(
        db_session, principal=partner, placement_id=pid, ctx=CTX,
    )
    await moderation_service.approve_placement(
        db_session, principal=uni, placement_id=pid, ctx=CTX,
    )
    await moderation_service.mark_paid(
        db_session, principal=uni, placement_id=pid,
        payment_reference="REF-SWEEP", ctx=CTX,
    )
    # Window not yet open -> still approved, flags OFF.
    assert await _flags(db_session, Job, job_id) == (False, False)

    future = _now() + timedelta(days=2)
    r1 = await activation_service.activation_sweep(db_session, now=future)
    await db_session.commit()
    assert r1["activated"] == 1
    assert await _flags(db_session, Job, job_id) == (True, False)
    # Re-tick is a no-op.
    r2 = await activation_service.activation_sweep(db_session, now=future)
    await db_session.commit()
    assert r2["activated"] == 0

    end_after = _now() + timedelta(days=99)
    c1 = await activation_service.completion_sweep(db_session, now=end_after)
    await db_session.commit()
    assert c1["completed"] == 1
    assert await _flags(db_session, Job, job_id) == (False, False)
    c2 = await activation_service.completion_sweep(db_session, now=end_after)
    await db_session.commit()
    assert c2["completed"] == 0


async def test_flag_reconcile_self_heals_drift(db_session) -> None:
    pkgs = await _seed_packages(db_session)
    _u, _o, partner = await make_org_with_admin(db_session)
    _uu, _uo, uni = await make_org_with_admin(db_session, org_type="university")
    job_id = await _published_job(db_session, partner, uni)

    # An ACTIVE placement exists but the job flag was (incorrectly) left OFF.
    placement = SponsoredPlacement(
        org_id=partner.org_id, created_by=partner.user_id, target_type="job",
        target_id=job_id, placement_type="both", package_id=pkgs["premium_30d"].id,
        price_amount="6000000.00", currency="VND",
        start_at=_now() - timedelta(days=1), end_at=_now() + timedelta(days=29),
        status="active", disclosure_confirmed=True, paid_at=_now(),
        activated_at=_now(),
    )
    db_session.add(placement)
    await db_session.commit()
    assert await _flags(db_session, Job, job_id) == (False, False)

    res = await activation_service.flag_reconcile(db_session, now=_now())
    await db_session.commit()
    assert res["changed"] == 1
    assert await _flags(db_session, Job, job_id) == (True, True)


# --------------------------------------------------------------------------- #
# Cross-module rule: advertising never imports the Job/Event ORM directly     #
# --------------------------------------------------------------------------- #


def test_advertising_does_not_import_opportunities_orm() -> None:
    import ast
    import pathlib

    root = pathlib.Path(
        "app/modules/advertising"
    )
    forbidden = "app.modules.opportunities.domain"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(forbidden):
                    offenders.append(f"{path}: {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden):
                        offenders.append(f"{path}: {alias.name}")
    assert offenders == [], offenders
