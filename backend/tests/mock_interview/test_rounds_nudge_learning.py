"""v3 upgrades — multi-round personas, real-time nudge, gap -> learning links.

Everything here is DETERMINISTIC and offline-safe (the whole suite runs with no
provider), proving each new LLM output has a complete no-model path:

- deterministic ROUND partition of the competency map (screening / technical /
  hiring_manager), clean and leak-safe;
- ROUND progression + ``current_round`` advancing as competencies are covered;
- the plan slice carries the CURRENT round persona into the conversation prompt;
- the answer NUDGE mapping (incl. the ``None`` "already strong" case);
- deterministic gap -> learning links present with no fabricated names/URLs;
- the NO-SCORE invariant preserved across rounds / nudge / learning;
- a full offline session is still complete (rounds + nudge + structured gaps).
"""

from __future__ import annotations

import json
import uuid

from app.ai.prompts.mock_interview import v1 as prompts
from app.modules.mock_interview.application import (
    caps,
    conversation_service,
    plan_service,
    report_service,
    session_service,
)

from tests.auth_utils import CTX
from tests.documents_utils import make_student
from tests.mock_interview._seed import make_public_job, make_strong_cv

_SCORE_KEYS = ("score", "rating", "grade", "percentage", "pass_fail", "points", "rank")


def _grounding_tech() -> dict:
    """A technical JD with a genuine gap so all three rounds materialise."""

    return {
        "locale": "en",
        "focus": "technical",
        "difficulty": "intermediate",
        "job": {
            "title": "Backend Engineer",
            "company_name": "Acme",
            "description": "Design and operate REST APIs.",
            "requirements": ["Design and operate REST APIs"],
            "required_skills": ["Python", "FastAPI", "PostgreSQL", "Kubernetes"],
            "seniority_level": "junior",
            "experience": "0-1 years",
        },
        "cv": {
            "title": "CS Intern CV",
            "language": "en",
            "highlights": ["[experience] Built REST APIs with FastAPI"],
            "skills": ["Python"],
        },
        "matched_skills": ["Python"],
        "gaps": ["Kubernetes"],
    }


# --------------------------------------------------------------------------- #
# 1) Deterministic ROUND partition                                            #
# --------------------------------------------------------------------------- #
def test_deterministic_plan_has_clean_round_partition() -> None:
    plan = plan_service._deterministic_plan(_grounding_tech())
    rounds = plan["rounds"]
    assert 1 <= len(rounds) <= caps.MAX_ROUNDS

    personas = [r["persona"] for r in rounds]
    assert all(p in caps.PERSONAS for p in personas)
    # Rounds keep natural interview order (screening before technical before HM).
    assert personas == sorted(personas, key=caps.PERSONAS.index)

    # A technical JD with a gap yields the full screening -> technical ->
    # hiring_manager progression.
    assert personas == ["screening", "technical", "hiring_manager"]

    # Clean partition: every competency lands in EXACTLY one round.
    all_ids = sorted(c["id"] for c in plan["competency_map"])
    round_ids = [cid for r in rounds for cid in r["competency_ids"]]
    assert sorted(round_ids) == all_ids
    assert len(round_ids) == len(set(round_ids))  # no competency in two rounds

    # The reserved hiring-manager round probes the genuine gap (Kubernetes).
    hm = next(r for r in rounds if r["persona"] == "hiring_manager")
    gap_id = next(
        c["id"] for c in plan["competency_map"] if str(c["cv_evidence"]).lower() == "gap"
    )
    assert hm["competency_ids"] == [gap_id]

    # Each round carries a localized label + valid shape.
    for r in rounds:
        assert set(r.keys()) == {"id", "label", "persona", "competency_ids"}
        assert r["label"] and r["competency_ids"]


def test_behavioral_jd_yields_two_rounds_no_technical() -> None:
    grounding = {"locale": "en", "focus": "behavioral", "job": {}, "cv": {}}
    plan = plan_service._deterministic_plan(grounding)
    personas = [r["persona"] for r in plan["rounds"]]
    # A behavioral JD has no technical competencies -> no technical round.
    assert "technical" not in personas
    assert "screening" in personas
    # Partition is still clean.
    round_ids = [cid for r in plan["rounds"] for cid in r["competency_ids"]]
    assert sorted(round_ids) == sorted(c["id"] for c in plan["competency_map"])


# --------------------------------------------------------------------------- #
# 2) Round progression + current_round                                        #
# --------------------------------------------------------------------------- #
def test_round_progression_advances_current_round() -> None:
    plan = plan_service._deterministic_plan(_grounding_tech())
    rounds = plan["rounds"]
    cov = plan_service.init_coverage(plan, difficulty="intermediate")

    # Starts on the first round, all rounds present, first active.
    assert cov["current_round"] == rounds[0]["id"]
    prog0 = plan_service.round_progress(plan, cov, "en")
    assert prog0 is not None
    assert prog0["current_round"] == rounds[0]["id"]
    assert prog0["rounds"][0]["status"] == "active"
    assert all(r["status"] == "upcoming" for r in prog0["rounds"][1:])

    seq = 1
    # Cover round 1's competencies -> pointer advances to round 2.
    for cid in rounds[0]["competency_ids"]:
        seq += 1
        cov = plan_service.record_interviewer_question(
            cov, plan, question_text="generic follow up", seq=seq, targeted_id=cid
        )
    assert cov["current_round"] == rounds[1]["id"]
    prog1 = plan_service.round_progress(plan, cov, "en")
    assert prog1 is not None
    assert prog1["rounds"][0]["status"] == "done"
    assert prog1["rounds"][1]["status"] == "active"
    assert prog1["current_round"] == rounds[1]["id"]

    # Cover everything -> current_round None, every round done.
    for r in rounds:
        for cid in r["competency_ids"]:
            seq += 1
            cov = plan_service.record_interviewer_question(
                cov, plan, question_text="generic", seq=seq, targeted_id=cid
            )
    assert cov["current_round"] is None
    prog2 = plan_service.round_progress(plan, cov, "en")
    assert prog2 is not None
    assert prog2["current_round"] is None
    assert all(r["status"] == "done" for r in prog2["rounds"])


def test_plan_slice_carries_current_round_persona_into_prompt() -> None:
    grounding = _grounding_tech()
    plan = plan_service._deterministic_plan(grounding)
    cov = plan_service.init_coverage(plan)

    sl = plan_service.build_plan_slice(plan, cov)
    assert sl is not None
    assert sl["round_id"] == plan["rounds"][0]["id"]
    assert sl["persona"] == "screening"  # first round persona

    system = prompts.build_conversation_system_prompt(
        grounding, target_questions=6, plan_slice=sl
    )
    # The screening persona voice is injected into the per-turn plan slice.
    assert "CURRENT ROUND" in system
    assert "SCREENING" in system
    # Static safety invariants still present alongside the persona block.
    for invariant in ("exactly ONE question", "[END]", "protected", "score"):
        assert invariant in system


def test_round_progress_is_leak_safe() -> None:
    """Only labels + status are exposed — no persona keys, ids, weights, scores."""

    # Build from a vi grounding so the localized labels never coincide with the
    # raw English persona KEYS we must not leak.
    grounding = {**_grounding_tech(), "locale": "vi"}
    plan = plan_service._deterministic_plan(grounding)
    cov = plan_service.init_coverage(plan)
    prog = plan_service.round_progress(plan, cov, "vi")
    assert prog is not None

    # Each round exposes ONLY the four leak-safe keys.
    for r in prog["rounds"]:
        assert set(r.keys()) == {"id", "label", "persona_label", "status"}
        assert r["persona_label"]  # localized, non-empty
        assert r["status"] in {"done", "active", "upcoming"}

    blob = json.dumps(prog, ensure_ascii=False).lower()
    for term in (
        "screening",  # raw persona keys (vi labels don't contain these)
        "technical",
        "hiring_manager",
        "persona\":",  # the internal persona field itself
        "competency_ids",
        "weight",
        "jd_evidence",
        "cv_evidence",
        *_SCORE_KEYS,
    ):
        assert term not in blob, f"round_progress leaked {term!r}"


# --------------------------------------------------------------------------- #
# 3) Real-time answer NUDGE mapping (incl. null)                              #
# --------------------------------------------------------------------------- #
def test_build_nudge_mapping_including_null() -> None:
    # shallow -> "add specifics"
    vi = conversation_service.build_nudge("shallow", False, "vi")
    en = conversation_service.build_nudge("shallow", False, "en")
    assert vi is not None and "cụ thể" in vi["text"]
    assert en is not None and "specific" in en["text"].lower()

    # solid WITHOUT STAR -> "try STAR"
    star_vi = conversation_service.build_nudge("solid", False, "vi")
    star_en = conversation_service.build_nudge("solid", False, "en")
    assert star_vi is not None and "STAR" in star_vi["text"]
    assert star_en is not None and "STAR" in star_en["text"]

    # already strong -> no nudge (None)
    assert conversation_service.build_nudge("solid", True, "vi") is None
    assert conversation_service.build_nudge("deep", False, "en") is None
    assert conversation_service.build_nudge("deep", True, "vi") is None

    # A nudge is a tip object, never a score.
    for depth, star in (("shallow", False), ("solid", False)):
        nudge = conversation_service.build_nudge(depth, star, "en")
        assert nudge is not None
        assert set(nudge.keys()) == {"text"}
        blob = json.dumps(nudge).lower()
        for key in _SCORE_KEYS:
            assert key not in blob


def test_deterministic_depth_reads() -> None:
    # blank / one-word -> shallow
    assert conversation_service._deterministic_depth("") == ("shallow", False)
    assert conversation_service._deterministic_depth("Yes.")[0] == "shallow"

    deep = (
        "During my internship I noticed the reporting endpoint was slow, so I "
        "decided to add a database index because the query was doing a full table "
        "scan; after profiling I added a composite index and it reduced the p95 "
        "latency by 45 percent, which improved the throughput of the service."
    )
    depth, _star = conversation_service._deterministic_depth(deep)
    assert depth == "deep"

    star_ans = (
        "In my final project I was responsible for the payments module. I "
        "implemented a retry mechanism and I built a reconciliation job, which "
        "reduced failed transactions and improved reliability across the checkout "
        "flow for our team."
    )
    _d, star = conversation_service._deterministic_depth(star_ans)
    assert star is True


async def test_read_answer_signal_offline_is_deterministic(db_session) -> None:
    sig = await conversation_service.read_answer_signal(
        db_session,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        question="Tell me about a project.",
        answer="Yes.",
        current_tier="intermediate",
    )
    assert sig["depth"] == "shallow"
    assert sig["star"] is False
    # A shallow answer eases the next tier down (adaptive difficulty).
    assert sig["next_tier"] == "foundational"
    # And it maps to an "add specifics" nudge deterministically (offline).
    nudge = conversation_service.build_nudge(sig["depth"], bool(sig["star"]), "en")
    assert nudge is not None and "specific" in nudge["text"].lower()


# --------------------------------------------------------------------------- #
# 4) Gap -> learning links (deterministic, honest)                            #
# --------------------------------------------------------------------------- #
def test_build_gap_learning_curated_and_generic() -> None:
    # Curated skill -> concrete topics.
    items = report_service.build_gap_learning("PostgreSQL / SQL", "en")
    assert 0 < len(items) <= report_service._MAX_LEARNING
    for it in items:
        assert set(it.keys()) == {"title", "kind"}
        assert it["kind"] in {"skill", "topic", "resource"}
    titles = " ".join(i["title"] for i in items).lower()
    assert "index" in titles  # curated SQL learning topic

    # Unknown skill -> honest GENERIC direction referencing the label, no fake URL.
    gen = report_service.build_gap_learning("Zorblax framework", "en")
    assert 0 < len(gen) <= report_service._MAX_LEARNING
    joined = " ".join(i["title"] for i in gen)
    assert "Zorblax" in joined  # grounded in the real gap label
    assert "http" not in joined.lower() and ".com" not in joined.lower()


def test_enrich_report_gaps_structured_and_idempotent() -> None:
    grounding = _grounding_tech()
    report = {
        "per_question": [],
        "overall_observations": "Good effort overall.",
        "gaps_to_work_on": ["Kubernetes", "Communication skills"],
        "strengths": ["Clear thinking"],
        "is_fallback": True,
    }
    enriched = report_service.enrich_report_gaps(report, grounding, "en")
    assert enriched is not None
    gaps = enriched["gaps_to_work_on"]
    assert gaps
    for g in gaps:
        assert set(g.keys()) == {"label", "why", "learning"}
        assert g["label"] and g["why"]
        assert g["learning"]
        for lk in g["learning"]:
            assert set(lk.keys()) == {"title", "kind"}
            assert lk["kind"] in {"skill", "topic", "resource"}

    # The stored report is NOT mutated -> repeated presenter calls are stable.
    assert report["gaps_to_work_on"] == ["Kubernetes", "Communication skills"]
    assert report_service.enrich_report_gaps(report, grounding, "en") == enriched

    # No score survives anywhere in the enriched report.
    blob = json.dumps(enriched, ensure_ascii=False).lower()
    for key in _SCORE_KEYS:
        assert f'"{key}"' not in blob


# --------------------------------------------------------------------------- #
# 5) Full OFFLINE session stays complete (rounds + nudge + learning)          #
# --------------------------------------------------------------------------- #
async def _seed(db):
    _u, student = await make_student(db)
    await make_strong_cv(db, student)
    job_id = await make_public_job(db)
    return student, job_id


async def test_offline_session_complete_with_rounds_nudge_learning(db_session) -> None:
    student, job_id = await _seed(db_session)

    created = await session_service.create_session(
        db_session, principal=student, ctx=CTX, job_id=job_id, cv_id=None
    )
    sid = uuid.UUID(created["session_id"])
    # Rounds surface on create, with the first round active.
    assert created["rounds"] is not None and created["rounds"]
    assert created["current_round"] == created["rounds"][0]["id"]
    assert created["rounds"][0]["status"] == "active"

    # A turn's done event carries a leak-safe nudge (dict or null) + live rounds.
    done = None
    async for ev in session_service.stream_turn(
        db_session, principal=student, session_id=sid, answer="Yes, I did."
    ):
        if ev["type"] == "done":
            done = ev
    assert done is not None
    assert "nudge" in done  # key always present (dict or None)
    assert "rounds" in done and "current_round" in done
    if done["nudge"] is not None:
        assert set(done["nudge"].keys()) == {"text"}
    # A short answer maps to the deterministic "add specifics" nudge (offline).
    assert done["nudge"] is not None and done["nudge"]["text"]
    blob = json.dumps(done, ensure_ascii=False).lower()
    for key in _SCORE_KEYS:
        assert f'"{key}"' not in blob

    # Ending yields a report whose gaps carry deterministic learning links.
    detail = await session_service.end_session(
        db_session, principal=student, ctx=CTX, session_id=sid, duration_seconds=60
    )
    report = detail["report"]
    assert report is not None
    assert report["gaps_to_work_on"]  # offline fallback is still gap-keyed
    for g in report["gaps_to_work_on"]:
        assert set(g.keys()) == {"label", "why", "learning"}
        assert g["learning"]
    # Detail still exposes the multi-round progress + no score anywhere.
    assert detail["rounds"] is not None
    detail_blob = json.dumps(detail, ensure_ascii=False).lower()
    for key in _SCORE_KEYS:
        assert f'"{key}"' not in detail_blob
