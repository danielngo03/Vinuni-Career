"""WS-12 Task F — guest personalization depth: weighting/decay, snapshots, search
unification, guest→login continuity, and the load-bearing privacy allowlist.

These cover the six acceptance criteria of the discovery signal-quality upgrade:

(a) frequency-weighting — a value viewed 20× out-ranks the same value viewed once;
(b) time-decay — a stale coarse tag decays and stops dominating a fresh interest;
(c) recommendation_snapshots persisted with honest source + reason codes + NO PII
    (no CV title/id, no provider/model/confidence, no forbidden reason fields);
(d) recent typed searches (``search_logs``) feed the ranker (store unification),
    without double-counting a term already recorded in the coarse tags;
(e) guest → login carries signals: the ``discovery_sessions.user_id`` link is set
    on login and the accumulated coarse signals personalize the student's recs;
(f) the default-deny allowlist still rejects forbidden PII/sensitive/3p-ad keys in
    the new weighted ``{value: {count, last_seen}}`` shape.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from app.modules.discovery.application import ranking_service, session_service
from app.modules.discovery.domain import allowlist, ranking
from app.modules.discovery.domain.models import RecommendationSnapshot
from app.modules.discovery.domain.search_log_model import SearchLog
from app.modules.documents.domain.models import CvSection
from app.shared.permissions import GUEST
from sqlalchemy import func, select

from tests.documents_utils import make_student
from tests.org_utils import make_org_with_admin
from tests.recruitment_utils import make_builder_cv, publish_job

_FORBIDDEN = [
    "openrouter", "openai", "anthropic", "claude", "gpt-4", "gemini", "deepseek",
    "prompt_tokens", "completion_tokens", "storage_path", "confidence", "embedding",
    "cv_title",
]


def _assert_no_leak(payload: object) -> None:
    blob = json.dumps(payload, ensure_ascii=False, default=str).lower()
    for term in _FORBIDDEN:
        assert term not in blob, f"leaked term: {term}"


def _now() -> datetime:
    return datetime.now(tz=UTC)


async def _university(db):
    _u, _org, uni = await make_org_with_admin(db, org_type="university")
    return uni


async def _partner(db, name: str):
    _u, _org, partner = await make_org_with_admin(db, display_name=name)
    return partner


async def _seed_cv_skills(db, cv_id: str, text: str) -> None:
    sections = (
        await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id)))
    ).scalars().all()
    target = next(s for s in sections if s.section_type == "skills")
    target.content_json = {"items": [{"text": text}]}
    await db.commit()


def _cat_tags(value: str, *, count: int, age_days: float = 0.0) -> dict:
    """A weighted coarse-tag cookie payload for one category value."""

    last_seen = (_now() - timedelta(days=age_days)).isoformat()
    return {"categories": {value: {"count": count, "last_seen": last_seen}}}


# --------------------------------------------------------------------------- #
# (a) + (b) — the pure weighting/decay policy                                 #
# --------------------------------------------------------------------------- #


def test_session_signal_weight_frequency_and_decay() -> None:
    # Frequency: many views out-weigh one (diminishing, bounded to 1.0).
    assert ranking.session_signal_weight(20, 0.0) > ranking.session_signal_weight(1, 0.0)
    assert ranking.session_signal_weight(20, 0.0) <= 1.0
    # Decay: a fresh tag out-weighs a month-old one of equal count.
    assert ranking.session_signal_weight(1, 0.0) > ranking.session_signal_weight(1, 29.0)
    # A month-old single glance has decayed to near-nothing.
    assert ranking.session_signal_weight(1, 29.0) < 0.05
    # Legacy presence-only rows (no last_seen) apply NO decay (back-compat).
    assert ranking.session_signal_weight(1, None) == ranking.session_signal_weight(1, 0.0)


# --------------------------------------------------------------------------- #
# (a) frequency-weighting end-to-end: Finance×20 out-ranks Finance×1          #
# --------------------------------------------------------------------------- #


async def test_frequency_weighting_changes_ranking_score(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Finance Analyst", required_skills=["finance"],
    )

    heavy = await ranking_service.recommend_jobs(
        db_session, principal=GUEST, cookie_tags=_cat_tags("finance", count=20)
    )
    once = await ranking_service.recommend_jobs(
        db_session, principal=GUEST, cookie_tags=_cat_tags("finance", count=1)
    )

    assert heavy["personalized"] is True and once["personalized"] is True
    heavy_score = heavy["items"][0]["score"]
    once_score = once["items"][0]["score"]
    # Finance viewed 20× produces a strictly higher product score than viewed once.
    assert heavy_score > once_score
    codes = {r["code"] for r in heavy["items"][0]["reason_codes"]}
    assert ranking.REASON_SIMILAR_INDUSTRY in codes


async def test_frequency_weighting_orders_two_categories(db_session) -> None:
    uni = await _university(db_session)
    pa = await _partner(db_session, "Org A")
    pb = await _partner(db_session, "Org B")
    fin = await publish_job(
        db_session, partner_principal=pa, uni_principal=uni,
        title="Finance Analyst", required_skills=["finance"],
    )
    mkt = await publish_job(
        db_session, partner_principal=pb, uni_principal=uni,
        title="Marketing Coordinator", required_skills=["marketing"],
    )
    # One session: Finance viewed 20×, Marketing viewed once.
    now = _now().isoformat()
    tags = {
        "categories": {
            "finance": {"count": 20, "last_seen": now},
            "marketing": {"count": 1, "last_seen": now},
        }
    }
    out = await ranking_service.recommend_jobs(
        db_session, principal=GUEST, cookie_tags=tags, limit=10
    )
    order = [it["id"] for it in out["items"]]
    # The heavily-viewed Finance interest ranks above the once-seen Marketing one.
    assert order.index(str(fin)) < order.index(str(mkt))


# --------------------------------------------------------------------------- #
# (b) time-decay end-to-end                                                   #
# --------------------------------------------------------------------------- #


async def test_time_decay_reduces_ranking_score(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Finance Analyst", required_skills=["finance"],
    )

    fresh = await ranking_service.recommend_jobs(
        db_session, principal=GUEST, cookie_tags=_cat_tags("finance", count=1, age_days=0)
    )
    stale = await ranking_service.recommend_jobs(
        db_session, principal=GUEST, cookie_tags=_cat_tags("finance", count=1, age_days=29)
    )
    # A 29-day-old glance no longer counts as a live, fresh interest.
    assert fresh["items"][0]["score"] > stale["items"][0]["score"]


# --------------------------------------------------------------------------- #
# (c) recommendation_snapshots persisted, reason codes, NO PII                 #
# --------------------------------------------------------------------------- #


async def test_snapshot_persisted_with_reason_codes_and_no_pii(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Python Backend Intern", required_skills=["python", "fastapi"],
    )
    _su, student = await make_student(db_session)
    sel = await make_builder_cv(db_session, student=student)
    await _seed_cv_skills(db_session, sel["cv_profile_id"], "Python, FastAPI, SQL")

    # A real live guest session so the snapshot's session FK resolves.
    sess = await session_service.get_or_create(db_session, cookie_id=None)
    await db_session.commit()

    out = await ranking_service.recommend_jobs(
        db_session,
        principal=student,
        cookie_tags={"search_terms": ["python"]},
        q="python",
        discovery_session_id=sess.id,
        snapshot_surface="jobs_recommendations",
    )
    # The RETURNED item carries the student's recommended CV (personalized).
    assert out["items"][0]["recommended_cv_id"] == sel["cv_profile_id"]

    snaps = (
        await db_session.execute(select(RecommendationSnapshot))
    ).scalars().all()
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap.surface == "jobs_recommendations"
    assert snap.list_source == out["source"]
    assert snap.scope == "user" and snap.user_id == student.user_id
    assert snap.item_count == len(snap.items) >= 1

    # Items carry job id + honest source + reason codes; NO CV-identifying / PII
    # fields leak into the audit substrate.
    for item in snap.items:
        assert item["job_id"]
        assert item["source"] in {"recommended", "recent", "popular", "sponsored"}
        assert "recommended_cv_id" not in item
        for reason in item["reason_codes"]:
            assert "cv_title" not in reason and "cv_id" not in reason
            assert set(reason) <= {"code", "value", "term", "skills", "days", "score"}
    _assert_no_leak(snap.items)


async def test_no_snapshot_written_off_serving_paths(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    await publish_job(db_session, partner_principal=partner, uni_principal=uni, title="Role")

    # Default call (e.g. the student dashboard) writes NO snapshot.
    await ranking_service.recommend_jobs(db_session, principal=GUEST)
    count = (
        await db_session.execute(select(func.count()).select_from(RecommendationSnapshot))
    ).scalar_one()
    assert count == 0


# --------------------------------------------------------------------------- #
# (d) search_logs unified with the ranker (no double-count)                    #
# --------------------------------------------------------------------------- #


async def test_recent_searches_feed_ranking(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Data Analyst Intern", required_skills=["sql", "excel"],
    )
    sess = await session_service.get_or_create(db_session, cookie_id=None)
    db_session.add(
        SearchLog(query="data analyst", locale="vi", session_id=sess.id)
    )
    await db_session.commit()

    # NO cookie_tags, NO q — only the typed-search history in search_logs.
    out = await ranking_service.recommend_jobs(
        db_session, principal=GUEST, discovery_session_id=sess.id
    )
    assert out["personalized"] is True
    codes = {r["code"] for it in out["items"] for r in it["reason_codes"]}
    assert ranking.REASON_MATCHES_SEARCH in codes


async def test_search_terms_not_double_counted(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Data Analyst Intern", required_skills=["sql"],
    )
    sess = await session_service.get_or_create(db_session, cookie_id=None)
    # Same term present in BOTH the coarse tags AND the search log.
    db_session.add(SearchLog(query="data analyst", locale="vi", session_id=sess.id))
    await db_session.commit()

    ctx = await ranking_service._build_ctx(
        db_session,
        principal=GUEST,
        cookie_tags={"search_terms": ["data analyst"]},
        q="data analyst",
        locale="vi",
        discovery_session_id=sess.id,
    )
    # De-duped by normalized form → the term appears exactly once (never counted
    # from both stores).
    normalized = ["data analyst".lower()]
    assert [t.lower() for t in ctx.query_terms] == normalized


# --------------------------------------------------------------------------- #
# (e) guest → login continuity                                                #
# --------------------------------------------------------------------------- #


async def test_link_user_on_login_sets_link(db_session) -> None:
    sess = await session_service.get_or_create(db_session, cookie_id=None)
    await session_service.record_signal(
        db_session, sess, tags={"categories": ["finance"]}
    )
    await db_session.commit()
    assert sess.user_id is None

    user_id = uuid.uuid4()
    linked = await session_service.link_user_on_login(
        db_session, cookie_id=str(sess.id), user_id=user_id
    )
    assert linked is not None and linked.user_id == user_id
    # The coarse signals are untouched by the link (continuity preserved).
    assert set(linked.coarse_tags) == {"categories"}

    # Idempotent: a second login never overwrites the existing link.
    again = await session_service.link_user_on_login(
        db_session, cookie_id=str(sess.id), user_id=uuid.uuid4()
    )
    assert again is not None and again.user_id == user_id


async def test_guest_signals_carry_into_authenticated_recommendations(db_session) -> None:
    uni = await _university(db_session)
    partner = await _partner(db_session, "Acme Co")
    await publish_job(
        db_session, partner_principal=partner, uni_principal=uni,
        title="Finance Analyst", required_skills=["finance"],
    )
    _su, student = await make_student(db_session)  # no CV / no prefs

    # The coarse signal accumulated as a guest personalizes the logged-in student's
    # recommendations (the delivery path reads the same first-party cookie tags).
    out = await ranking_service.recommend_jobs(
        db_session, principal=student, cookie_tags=_cat_tags("finance", count=5)
    )
    assert out["personalized"] is True
    assert out["source"] == ranking.SOURCE_RECOMMENDED
    codes = {r["code"] for it in out["items"] for r in it["reason_codes"]}
    assert ranking.REASON_SIMILAR_INDUSTRY in codes


async def test_link_user_on_login_missing_cookie_is_noop(db_session) -> None:
    # A student who never browsed as a guest → no session → quiet no-op.
    linked = await session_service.link_user_on_login(
        db_session, cookie_id=None, user_id=uuid.uuid4()
    )
    assert linked is None


# --------------------------------------------------------------------------- #
# (f) allowlist still rejects forbidden keys in the weighted shape             #
# --------------------------------------------------------------------------- #


def test_weighted_merge_still_rejects_forbidden_keys() -> None:
    raw = {
        "categories": ["finance"],
        "email": "leak@example.com",
        "ip": "203.0.113.7",
        "gps": "21.0,105.8",
        "cv_text": "raw cv body",
        "gaid": "ad-id-123",
        "salary": "50000",
    }
    merged = allowlist.merge_coarse_tags({}, raw)
    assert set(merged) == {"categories"}
    assert set(merged["categories"]) == {"finance"}
    for forbidden in allowlist.FORBIDDEN_COARSE_TAG_KEYS:
        assert forbidden not in merged
    # The weighted entry is a bounded {count, last_seen} — never raw text/PII.
    entry = merged["categories"]["finance"]
    assert set(entry) == {"count", "last_seen"}
    assert isinstance(entry["count"], int)


def test_weighted_entries_reads_legacy_and_new_shapes() -> None:
    # Legacy bare-list row → count=1, no last_seen (no decay applied downstream).
    legacy = allowlist.weighted_entries({"categories": ["finance"]}, "categories")
    assert legacy == [("finance", 1, None)]
    # New weighted row round-trips count + last_seen.
    ts = _now().isoformat()
    entries = allowlist.weighted_entries(
        {"categories": {"finance": {"count": 7, "last_seen": ts}}}, "categories"
    )
    assert entries == [("finance", 7, ts)]
    # Count is clamped to a sane bound (a single burst can never overflow).
    huge = allowlist.weighted_entries(
        {"categories": {"finance": {"count": 10**9}}}, "categories"
    )
    assert huge[0][1] <= 1000
