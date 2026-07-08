"""Task G — student assistant loop-closing write tools + i18n + isolation.

Covers the four confirmation-gated STUDENT write tools added in WS-10:
``tailor_cv_to_job``, ``draft_and_attach_cover_letter``, ``set_job_alert``,
``register_for_event``. Asserts, offline (no real-model calls):

- each tool is ``confirmation_required`` + student-only with the full §7 contract;
- a confirmation is required BEFORE execute (confirm-flow), and the underlying
  write + audit row only happen on confirm;
- the metered tools debit the student's AI energy on success;
- confirmation-card copy renders BOTH vi and en (locale-driven contract);
- student isolation: only STUDENT tools are exposed, no upload/web/external tool
  exists, and the KB tool stays internal.
"""

from __future__ import annotations

import json
import types
import uuid
from unittest import mock

from app.ai.gateway.base import AICompletion
from app.ai.observability.models import AiBillableUsage
from app.modules.ai_assistant.application.tool_loop import (
    confirm_tool_action,
    make_confirmation_message,
)
from app.modules.ai_assistant.application.tools import cv_ai, events, jobs
from app.modules.ai_assistant.application.tools.dispatch import SUPPORTED_TOOL_NAMES
from app.modules.ai_assistant.application.tools.specs import (
    PARTNER_USER,
    STUDENT,
    TOOL_SPECS,
    UNIVERSITY_STAFF,
)
from app.modules.documents.domain.models import CvAiSuggestion
from app.modules.opportunities.domain.event_models import EventRegistration
from app.modules.opportunities.domain.models import JobAlert
from app.shared.models import AuditLog
from sqlalchemy import func, select
from tests.auth_utils import CTX
from tests.documents_utils import make_ready_cv, make_student
from tests.events_utils import publish_event
from tests.org_utils import make_org_with_admin

NEW_WRITE_TOOLS = (
    "tailor_cv_to_job",
    "draft_and_attach_cover_letter",
    "set_job_alert",
    "register_for_event",
)


# --------------------------------------------------------------------------- #
# Registry contract (no DB)                                                    #
# --------------------------------------------------------------------------- #


def test_new_write_tools_are_confirmation_gated_and_student_only() -> None:
    for name in NEW_WRITE_TOOLS:
        assert name in TOOL_SPECS, f"{name} missing from TOOL_SPECS"
        assert name in SUPPORTED_TOOL_NAMES, f"{name} missing from dispatch registry"
        spec = TOOL_SPECS[name]
        assert spec.permission_class == "confirmation_required", (
            f"{name} must be confirmation_required (§4.3)"
        )
        assert spec.persona == [STUDENT], f"{name} must be student-only"
        assert "role:student" in spec.required_permissions
        assert spec.side_effects, f"{name} must declare side_effects (§7)"
        assert spec.confirmation_copy is not None, f"{name} must declare confirmation_copy"
        assert spec.audit_event_type.startswith("TOOL_")
        assert spec.fallback, f"{name} must declare fallback text"


# --------------------------------------------------------------------------- #
# Student isolation (no DB)                                                    #
# --------------------------------------------------------------------------- #


def test_student_session_exposes_only_student_tools() -> None:
    """The assistant prompt only advertises tools whose persona includes STUDENT."""
    from app.ai.prompts.assistant.v1 import _STUDENT_TOOL_SPECS

    # Every advertised tool is student-facing …
    for name, spec in _STUDENT_TOOL_SPECS.items():
        assert STUDENT in spec.persona, f"{name} advertised to student but not student persona"

    # … and every partner/university-only tool is NEVER advertised to the student.
    for name, spec in TOOL_SPECS.items():
        restricted_only = spec.persona in ([PARTNER_USER], [UNIVERSITY_STAFF]) or (
            STUDENT not in spec.persona
        )
        if restricted_only:
            assert name not in _STUDENT_TOOL_SPECS, (
                f"{name} is not a student tool but leaked into the student prompt"
            )

    # Concretely: known partner-only tools must not be selectable by a student.
    for partner_tool in ("move_candidate_stage", "search_partner_candidates",
                         "get_partner_jobs", "suggest_scorecard"):
        assert partner_tool not in _STUDENT_TOOL_SPECS

    # The new write tools ARE selectable by the student.
    for name in NEW_WRITE_TOOLS:
        assert name in _STUDENT_TOOL_SPECS


def test_no_upload_or_web_or_external_tool_exists() -> None:
    """There is no file-upload tool and no web/browse/external-search tool."""
    forbidden_fragments = (
        "upload", "web_search", "browse", "internet", "fetch_url", "http",
        "google", "linkedin", "indeed", "glassdoor", "external",
    )
    for name in TOOL_SPECS:
        lowered = name.lower()
        for frag in forbidden_fragments:
            assert frag not in lowered, f"tool {name!r} looks like an upload/web/external tool"


def test_knowledge_base_query_is_internal_only() -> None:
    """The only KB tool is the internal-KB query; it never advertises the web."""
    spec = TOOL_SPECS["knowledge_base_query"]
    desc = spec.description.lower()
    assert "knowledge base" in desc
    assert "internet" not in desc and "web" not in desc
    # No second/external KB or search tool sneaked in.
    kb_like = [n for n in TOOL_SPECS if "knowledge" in n or n.endswith("_kb")]
    assert kb_like == ["knowledge_base_query"]


# --------------------------------------------------------------------------- #
# i18n confirmation-card copy (no DB)                                          #
# --------------------------------------------------------------------------- #


def _fake_chat() -> object:
    return types.SimpleNamespace(id=uuid.uuid4())


def test_confirmation_card_copy_is_locale_driven_vi_and_en() -> None:
    chat = _fake_chat()
    for name in NEW_WRITE_TOOLS:
        vi = make_confirmation_message(chat, tool_name=name, tool_args={}, locale="vi")
        en = make_confirmation_message(chat, tool_name=name, tool_args={}, locale="en")
        assert vi.content.strip() and en.content.strip()
        assert vi.content != en.content, f"{name} card is not localized (vi == en)"
        assert vi.requires_confirmation and en.requires_confirmation


def test_confirmation_copy_renders_expected_language_tokens() -> None:
    copy = TOOL_SPECS["register_for_event"].confirmation_copy
    assert copy is not None
    assert "Đăng ký" in copy.localized("vi")["title"]
    assert "Register" in copy.localized("en")["title"]
    alert = TOOL_SPECS["set_job_alert"].confirmation_copy
    assert alert is not None
    assert "thông báo việc làm" in alert.localized("vi")["body"].lower()
    assert "job alert" in alert.localized("en")["body"].lower()
    # Unknown locale falls back to vi (byte-identical historical behaviour).
    assert copy.localized("fr")["title"] == copy.localized("vi")["title"]


# --------------------------------------------------------------------------- #
# register_for_event: confirmation required BEFORE execute + audit on confirm  #
# --------------------------------------------------------------------------- #


async def _publish_event(db):
    _pu, _porg, partner = await make_org_with_admin(db, org_type="partner")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    event_id = await publish_event(db, partner, uni, title="AI Careers Day")
    return event_id


async def test_register_for_event_requires_confirmation_then_writes(db_session) -> None:
    from app.modules.ai_assistant.application import chat_service
    from app.modules.ai_assistant.application.session_history import require_session

    _u, student = await make_student(db_session)
    event_id = await _publish_event(db_session)

    created = await chat_service.create_session(db_session, principal=student)
    session_id = uuid.UUID(created["id"])
    chat = await require_session(db_session, student, session_id)

    # The assistant surfaces a pending confirmation card — nothing is executed yet.
    pending = make_confirmation_message(
        chat, tool_name="register_for_event",
        tool_args={"event_id": str(event_id)}, locale="en",
    )
    db_session.add(pending)
    await db_session.commit()

    before = (
        await db_session.execute(
            select(func.count()).select_from(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == student.user_id,
            )
        )
    ).scalar_one()
    assert before == 0, "registration must NOT happen before confirmation"

    # Confirm -> the tool executes.
    out = await confirm_tool_action(
        db_session, principal=student, session_id=session_id,
        message_id=pending.id, locale="en",
    )
    assert out["confirmed"]["tool_result"]["ok"] is True

    after = (
        await db_session.execute(
            select(func.count()).select_from(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == student.user_id,
            )
        )
    ).scalar_one()
    assert after == 1, "confirmation must create exactly one registration"

    audit = (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "event.registered",
            )
        )
    ).scalar_one()
    assert audit >= 1, "the write must create an audit row"


async def test_register_for_event_is_idempotent_on_reconfirm(db_session) -> None:
    _u, student = await make_student(db_session)
    event_id = await _publish_event(db_session)

    r1 = await events.register_for_event(
        db_session, student, {"event_id": str(event_id)}
    )
    r2 = await events.register_for_event(
        db_session, student, {"event_id": str(event_id)}
    )
    assert r1["ok"] and r2["ok"]
    count = (
        await db_session.execute(
            select(func.count()).select_from(EventRegistration).where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == student.user_id,
            )
        )
    ).scalar_one()
    assert count == 1


# --------------------------------------------------------------------------- #
# set_job_alert: deterministic write + audit                                   #
# --------------------------------------------------------------------------- #


async def test_set_job_alert_creates_alert_and_audit(db_session) -> None:
    _u, student = await make_student(db_session)

    result = await jobs.set_job_alert(
        db_session, student,
        {"keywords": "data analyst", "employment_type": "internship",
         "location_type": "remote"},
    )
    assert result["ok"] is True and result["created"] is True

    alerts = (
        await db_session.execute(
            select(JobAlert).where(JobAlert.user_id == student.user_id)
        )
    ).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].keywords == "data analyst"

    audit = (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "job_alert.created",
                AuditLog.resource_id == alerts[0].id,
            )
        )
    ).scalar_one()
    assert audit == 1


async def test_set_job_alert_duplicate_name_is_user_safe(db_session) -> None:
    _u, student = await make_student(db_session)
    args = {"keywords": "backend", "name": "Backend roles"}
    first = await jobs.set_job_alert(db_session, student, args)
    assert first["ok"]
    dup = await jobs.set_job_alert(db_session, student, args)
    assert dup["ok"] is False
    assert dup["error"] == "alert_name_exists"


# --------------------------------------------------------------------------- #
# draft_and_attach_cover_letter: metered draft + apply hand-off                #
# --------------------------------------------------------------------------- #


async def _publish_job(db, *, title="Backend Intern"):
    from app.modules.opportunities.application import job_service, moderation_service

    _pu, _porg, partner = await make_org_with_admin(db, org_type="partner")
    _uu, _uorg, uni = await make_org_with_admin(db, org_type="university")
    payload = {
        "title": title,
        "description": "Build backend services in Python and SQL.",
        "requirements": None,
        "benefits": None,
        "employment_type": "internship",
        "location_type": "remote",
        "location_city": "Hanoi",
        "location_country": "Vietnam",
        "required_skills": ["python", "sql"],
        "preferred_skills": [],
        "experience_min_years": None,
        "experience_max_years": None,
        "degree_required": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "VND",
        "salary_is_disclosed": False,
        "headcount": 1,
        "application_deadline": None,
        "visibility": "public",
    }
    created = await job_service.create_job(db, principal=partner, payload=payload, ctx=CTX)
    jid = uuid.UUID(created["id"])
    await job_service.submit_job(db, principal=partner, job_id=jid, ctx=CTX)
    await moderation_service.approve_job(db, principal=uni, job_id=jid, ctx=CTX)
    return jid


async def _units(db, user_id, feature_key) -> int:
    total = (
        await db.execute(
            select(func.coalesce(func.sum(AiBillableUsage.units_charged), 0)).where(
                AiBillableUsage.actor_user_id == user_id,
                AiBillableUsage.feature_key == feature_key,
            )
        )
    ).scalar_one()
    return int(total or 0)


async def test_draft_and_attach_cover_letter_charges_energy_and_returns_attach(
    db_session,
) -> None:
    _u, student = await make_student(db_session)
    job_id = await _publish_job(db_session, title="Data Analyst Intern")

    result = await cv_ai.draft_and_attach_cover_letter(
        db_session, student, {"job_id": str(job_id)}
    )
    await db_session.commit()

    assert result["ok"] is True
    assert result["draft"].strip()
    # Loop-closing hand-off for the confirmation-gated apply flow.
    assert result["attach"]["tool"] == "apply_job"
    assert result["attach"]["args"]["job_id"] == str(job_id)
    assert result["attach"]["args"]["cover_letter"] == result["draft"]

    # Metered: a successful offline draft debits one cover-letter charge.
    assert await _units(db_session, student.user_id, "cover_letter") == 3


async def test_draft_and_attach_cover_letter_is_student_only(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, org_type="partner")
    out = await cv_ai.draft_and_attach_cover_letter(
        db_session, partner, {"job_id": str(uuid.uuid4())}
    )
    assert out["ok"] is False
    assert out["error"] == "student_only"


# --------------------------------------------------------------------------- #
# tailor_cv_to_job: pending diff (never auto-applied) + metered                #
# --------------------------------------------------------------------------- #


class _ScriptedCvProvider:
    """Offline provider returning valid CV edit-command operations JSON."""

    async def complete(self, *args, **kwargs) -> AICompletion:
        payload = {
            "operations": [
                {
                    "op": "add_item_text",
                    "section_type": "summary",
                    "text": "Backend developer with Python and SQL experience.",
                }
            ],
            "explanation": "Tailored the summary toward the role.",
        }
        return AICompletion(text=json.dumps(payload), model_alias="offline")


async def test_tailor_cv_to_job_returns_pending_diff_and_charges(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await make_ready_cv(db_session, student=student, title="My CV")
    cv_id = uuid.UUID(cv["id"])
    job_id = await _publish_job(db_session)

    with mock.patch("app.ai.cv.llm.get_provider", lambda: _ScriptedCvProvider()):
        result = await cv_ai.tailor_cv_to_job(
            db_session, student, {"job_id": str(job_id), "cv_id": str(cv_id)}
        )

    assert result["ok"] is True
    assert result["status"] == "pending"
    assert result["requires_confirmation"] is True
    assert result["suggestion_id"]

    # A PENDING suggestion exists and was NEVER auto-applied.
    suggestion = (
        await db_session.execute(
            select(CvAiSuggestion).where(CvAiSuggestion.cv_id == cv_id)
        )
    ).scalar_one()
    assert suggestion.status == "pending"
    assert suggestion.applied_version_id is None

    # Metered via the cv_edit_command feature.
    assert await _units(db_session, student.user_id, "cv_edit_command") == 2


async def test_tailor_cv_to_job_ai_unavailable_is_graceful(db_session) -> None:
    """Offline (no scripted ops) -> friendly ai_unavailable, no crash, no charge."""
    _u, student = await make_student(db_session)
    cv = await make_ready_cv(db_session, student=student, title="My CV")
    cv_id = uuid.UUID(cv["id"])
    job_id = await _publish_job(db_session)

    result = await cv_ai.tailor_cv_to_job(
        db_session, student, {"job_id": str(job_id), "cv_id": str(cv_id)}
    )
    assert result["ok"] is False
    assert result["error"] == "ai_unavailable"
    # No suggestion was persisted and nothing was charged.
    count = (
        await db_session.execute(
            select(func.count()).select_from(CvAiSuggestion).where(
                CvAiSuggestion.cv_id == cv_id
            )
        )
    ).scalar_one()
    assert count == 0
    assert await _units(db_session, student.user_id, "cv_edit_command") == 0


async def test_tailor_cv_to_job_is_student_only(db_session) -> None:
    _pu, _porg, partner = await make_org_with_admin(db_session, org_type="partner")
    out = await cv_ai.tailor_cv_to_job(
        db_session, partner, {"job_id": str(uuid.uuid4())}
    )
    assert out["ok"] is False
    assert out["error"] == "student_only"
