"""Executors for the recruiting-automation node types (Wave 2B).

Kept OUT of ``execution_service`` so the engine core stays free of cross-module
imports and so this file is the single place the ``workflow`` module reaches into
recruitment / documents / notifications — always through APPROVED application-layer
seams (facades / services), never a sibling ``domain.models`` / ``infrastructure``
import (enforced by ``tests/integration/test_module_boundaries.py``).

Safety model (docs/PARTNER_RBAC_ANALYTICS_SPEC.md + CLAUDE.md workflow rules):

- ``simulate=True`` is a strict no-op: no model spend, no stage move, no
  notification enqueued, no draft persisted. Dry-run reports what WOULD happen.
- Consequential/AI/write nodes run autonomously only AFTER explicit, RBAC-gated
  activation (``activation_service`` verified the activator holds every node's
  capability). At EXECUTION time the effective identity is re-resolved from the
  flow author's LIVE org grants (:func:`_automation_principal`) — so revoking the
  author's grant STOPS the automation rather than acting on stale authority.
- ``jd_pdf_to_draft`` never creates/publishes a job; it prepares a draft PROPOSAL
  and pauses for human confirm-create (``awaiting_human_review``).
- No provider/model/token/latency/prompt/raw-CV leakage: only user-safe fields
  (recommendation, deterministic match score, curated JD skill strings) surface.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import application_fit_service
from app.modules.notifications.application.dispatch_service import enqueue_notification
from app.modules.organization.application import grant_resolver
from app.modules.recruitment.application import automation_facade, cv_evaluation_service
from app.modules.workflow.application.errors import NodeExecutionFailed
from app.modules.workflow.domain.graph import FlowContext
from app.modules.workflow.domain.models import WorkflowFlow
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError
from app.shared.permissions import Principal

# Synthetic request context for autonomous (non-HTTP) automation runs. No real
# client IP / UA exists; services hash these before persistence anyway.
_AUTOMATION_CTX = RequestContext(ip=None, user_agent="workflow-automation")


@dataclass(slots=True)
class NodeOutcome:
    """A node handler's result: the branch ``decision`` (edge-routing token) plus
    the leak-safe ``output`` variables merged into the flow context."""

    decision: str
    output: dict = field(default_factory=dict)


async def execute(
    session: AsyncSession,
    *,
    flow: WorkflowFlow | None,
    node: dict,
    context: FlowContext,
    simulate: bool,
) -> NodeOutcome:
    node_type = node["type"]
    if node_type == "ai_screen_application":
        return await _screen_application(
            session, flow=flow, node=node, context=context, simulate=simulate
        )
    if node_type == "auto_advance_on_gate":
        return await _auto_advance(
            session, flow=flow, node=node, context=context, simulate=simulate
        )
    if node_type == "notify":
        return await _notify(session, flow=flow, node=node, context=context, simulate=simulate)
    if node_type == "jd_pdf_to_draft":
        return await _jd_pdf_to_draft(node=node, context=context)
    raise NodeExecutionFailed("Loại node quy trình không được hỗ trợ.")


# --------------------------------------------------------------------------- #
# Automation identity                                                          #
# --------------------------------------------------------------------------- #


async def _automation_principal(
    session: AsyncSession, *, flow: WorkflowFlow | None
) -> Principal | None:
    """The effective identity for an autonomous write/AI node: the flow author's
    LIVE org grants, re-resolved at execution time.

    Returns ``None`` when the author no longer has an active membership in the
    owning org (grant revoked / membership removed) — the caller then fails the
    node closed instead of acting on stale authorization.
    """

    if flow is None or flow.owner_org_id is None or flow.created_by is None:
        return None
    membership = await grant_resolver.active_membership(
        session, user_id=flow.created_by, org_id=flow.owner_org_id
    )
    if membership is None:
        return None
    grants = await grant_resolver.grants_for_membership(session, membership_id=membership.id)
    persona = "university_staff" if flow.owner_type == "university" else "partner_member"
    return Principal(
        user_id=flow.created_by,
        persona=persona,
        org_id=flow.owner_org_id,
        permissions=grants,
    )


def _trigger_application_id(node: dict, context: FlowContext) -> uuid.UUID | None:
    """Resolve the application this node acts on from the trigger payload (or a
    node-configured ``application_id_variable`` override)."""

    data = node.get("data", {})
    var = data.get("application_id_variable")
    raw: object = None
    if var:
        raw = context.variables.get(var) or context.trigger.get(var)
    if raw is None:
        raw = context.trigger.get("application_id")
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# ai_screen_application                                                        #
# --------------------------------------------------------------------------- #


def _recommendation_from_score(score: int | None, data: dict) -> str:
    if not isinstance(score, int):
        return "not_computable"
    strong = float(data.get("strong_threshold", 80))
    consider = float(data.get("consider_threshold", 50))
    if score >= strong:
        return "strong"
    if score >= consider:
        return "consider"
    return "weak"


async def _screen_application(
    session: AsyncSession,
    *,
    flow: WorkflowFlow | None,
    node: dict,
    context: FlowContext,
    simulate: bool,
) -> NodeOutcome:
    """Screen a triggered application against its JD; branch on the recommendation.

    Deterministic mode (default): the free, pure CV<->JD fit engine — no model
    spend, no principal needed. LLM mode: the metered on-demand HR evaluation
    (``cv_evaluation_service``), which carries its OWN ``UsageContext`` budget
    pre-check + durable idempotent ledger and its own deterministic fallback when
    AI is down. LLM mode NEVER spends on the simulate path.

    Decision (edge-routing token): ``strong`` | ``consider`` | ``weak`` |
    ``not_computable``. "Hold" is simply the absence of a matching edge.
    """

    data = node.get("data", {})
    locale = str(data.get("locale") or "vi")
    mode = data.get("mode", "deterministic")

    app_id = _trigger_application_id(node, context)
    if app_id is None:
        return NodeOutcome("not_computable", {"screen_reason": "no_application"})

    ref = await automation_facade.application_screening_ref(session, application_id=app_id)
    if ref is None:
        return NodeOutcome("not_computable", {"screen_reason": "no_snapshot"})

    # Deterministic fit signals (free, no principal) — grounds every mode.
    signals = await application_fit_service.application_snapshot_fit_signals(
        session, snapshot_id=ref["snapshot_id"], job_id=ref["job_id"], locale=locale
    )
    if signals is None:
        return NodeOutcome("not_computable", {"screen_reason": "not_scorable"})
    det_score = signals.get("score") if isinstance(signals.get("score"), int) else None

    if mode == "llm" and not simulate:
        principal = await _automation_principal(session, flow=flow)
        if principal is None:
            raise NodeExecutionFailed(
                "Không thể chạy đánh giá AI: quyền tự động hoá không còn hợp lệ."
            )
        try:
            verdict = await cv_evaluation_service.evaluate_candidate_cv(
                session,
                principal=principal,
                application_id=app_id,
                ctx=_AUTOMATION_CTX,
                refresh=False,
                locale=locale,
            )
        except (PermissionDeniedError, AuthRequiredError) as exc:
            raise NodeExecutionFailed(
                "Không thể chạy đánh giá AI: thiếu quyền đối với ứng viên này."
            ) from exc
        recommendation = verdict.get("recommendation") or _recommendation_from_score(
            det_score, data
        )
        raw_match = verdict.get("match_score")
        match_score = raw_match if isinstance(raw_match, int) else det_score
        return NodeOutcome(
            str(recommendation),
            {
                "screen_recommendation": recommendation,
                "screen_score": match_score,
                "screen_is_fallback": bool(verdict.get("is_fallback")),
            },
        )

    # Deterministic branch (also the safe simulate path for llm mode).
    recommendation = _recommendation_from_score(det_score, data)
    output: dict = {
        "screen_recommendation": recommendation,
        "screen_score": det_score,
        "screen_band": signals.get("band"),
        "screen_matched": list(signals.get("matched_skills") or [])[:8],
        "screen_gaps": list(signals.get("gaps") or [])[:8],
    }
    if simulate and mode == "llm":
        output["screen_simulated_llm"] = True
    return NodeOutcome(recommendation, output)


# --------------------------------------------------------------------------- #
# auto_advance_on_gate                                                         #
# --------------------------------------------------------------------------- #


async def _auto_advance(
    session: AsyncSession,
    *,
    flow: WorkflowFlow | None,
    node: dict,
    context: FlowContext,
    simulate: bool,
) -> NodeOutcome:
    """Advance the candidate to the next stage ONLY if the stage gate is met.

    Never bypasses ``gate_met``: the real path reuses the manual advance code path
    (same RBAC + same gate). The advance is made idempotent per (flow, node,
    application) so a re-fired trigger cannot double-advance. Decision:
    ``advanced`` | ``gate_not_met`` | ``not_applicable`` | ``not_found``.
    """

    locale = str(node.get("data", {}).get("locale") or "vi")
    app_id = _trigger_application_id(node, context)
    if app_id is None:
        return NodeOutcome("not_applicable", {"advance_reason": "no_application"})

    if simulate:
        gate = await automation_facade.evaluate_stage_gate(session, application_id=app_id)
        if not gate.get("applicable"):
            return NodeOutcome("not_applicable", {"advance_reason": gate.get("reason")})
        would = bool(gate.get("gate_met"))
        return NodeOutcome(
            "advanced" if would else "gate_not_met",
            {
                "advance_simulated": True,
                "would_advance": would,
                "advance_reason": gate.get("reason"),
            },
        )

    principal = await _automation_principal(session, flow=flow)
    if principal is None:
        raise NodeExecutionFailed(
            "Không thể chuyển giai đoạn tự động: quyền tự động hoá không còn hợp lệ."
        )
    assert flow is not None
    idem = f"wf:{flow.id}:{node['id']}:{app_id}"
    result = await automation_facade.auto_advance_if_gate_met(
        session,
        principal=principal,
        application_id=app_id,
        ctx=_AUTOMATION_CTX,
        idempotency_key=idem,
        locale=locale,
    )
    if result["advanced"]:
        return NodeOutcome("advanced", {"advanced": True})
    return NodeOutcome(
        str(result["reason"] or "gate_not_met"),
        {"advanced": False, "advance_reason": result["reason"]},
    )


# --------------------------------------------------------------------------- #
# notify                                                                       #
# --------------------------------------------------------------------------- #

_SAFE_VAR_KEYS = frozenset(
    {
        "application_id",
        "job_id",
        "org_id",
        "to_order",
        "screen_recommendation",
        "screen_score",
        "screen_band",
    }
)


def _safe_notify_vars(context: FlowContext) -> dict[str, object]:
    """A small, leak-safe variable payload for the notification template — only
    ids / recommendation / coarse score, never CV text or applicant PII."""

    out: dict[str, object] = {}
    for key in _SAFE_VAR_KEYS:
        value = context.variables.get(key, context.trigger.get(key))
        if isinstance(value, str | int | float | bool):
            out[key] = value
    return out


async def _resolve_recipient(
    session: AsyncSession, *, node: dict, context: FlowContext
) -> uuid.UUID | None:
    data = node.get("data", {})
    mode = data.get("recipient_mode", "assignee")
    if mode == "assignee":
        app_id = _trigger_application_id(node, context)
        if app_id is None:
            return None
        return await automation_facade.resolve_assignee_user_id(session, application_id=app_id)
    if mode == "user":
        raw = data.get("recipient_user_id")
        try:
            return uuid.UUID(str(raw))
        except (ValueError, AttributeError, TypeError):
            return None
    if mode == "trigger_var":
        var = data.get("recipient_variable", "")
        raw = context.variables.get(var) or context.trigger.get(var)
        try:
            return uuid.UUID(str(raw)) if raw is not None else None
        except (ValueError, AttributeError, TypeError):
            return None
    return None


async def _notify(
    session: AsyncSession,
    *,
    flow: WorkflowFlow | None,
    node: dict,
    context: FlowContext,
    simulate: bool,
) -> NodeOutcome:
    """Enqueue an in-app/email notification (outbox — never synchronous SMTP) to a
    resolved recipient (assignee / explicit user / trigger variable)."""

    data = node.get("data", {})
    template_key = data.get("template_key")
    if not template_key:
        raise NodeExecutionFailed("Không thể gửi thông báo: thiếu mẫu thông báo.")

    recipient_id = await _resolve_recipient(session, node=node, context=context)

    if simulate:
        return NodeOutcome(
            "simulated",
            {
                "notify_template": template_key,
                "notify_recipient_resolved": recipient_id is not None,
            },
        )

    if recipient_id is None:
        raise NodeExecutionFailed("Không thể gửi thông báo: không xác định được người nhận.")

    dedupe = None
    if flow is not None:
        dedupe = f"wf_notify:{flow.id}:{node['id']}:{recipient_id}"
    try:
        await enqueue_notification(
            session,
            recipient_id=recipient_id,
            template_key=str(template_key),
            channel=str(data.get("channel", "email")),
            locale=str(data.get("locale", "vi")),
            variables=_safe_notify_vars(context),
            dedupe_key=dedupe,
        )
    except Exception as exc:  # noqa: BLE001 — convert to a user-safe, recoverable failure
        raise NodeExecutionFailed("Không thể gửi thông báo do lỗi hệ thống.") from exc
    return NodeOutcome("sent", {"notification_sent": True})


# --------------------------------------------------------------------------- #
# jd_pdf_to_draft                                                              #
# --------------------------------------------------------------------------- #

_DRAFT_STR_FIELDS = ("title", "location", "employment_type", "seniority", "department")
_DRAFT_LIST_FIELDS = ("required_skills", "preferred_skills", "responsibilities")


def _normalize_draft_proposal(jd_fields: object) -> dict | None:
    """Project extracted JD fields into a compact job-draft PROPOSAL (or ``None``).

    Only structured, partner-authored JD content — no applicant/candidate data.
    """

    if not isinstance(jd_fields, dict) or not jd_fields:
        return None
    proposal: dict = {}
    for key in _DRAFT_STR_FIELDS:
        value = jd_fields.get(key)
        if isinstance(value, str) and value.strip():
            proposal[key] = value.strip()[:200]
    description = jd_fields.get("description")
    if isinstance(description, str) and description.strip():
        proposal["description"] = description.strip()[:4000]
    for key in _DRAFT_LIST_FIELDS:
        value = jd_fields.get(key)
        if isinstance(value, list):
            proposal[key] = [str(v)[:120] for v in value if v][:20]
    return proposal or None


async def _jd_pdf_to_draft(*, node: dict, context: FlowContext) -> NodeOutcome:
    """Turn extracted JD fields into a job-draft PROPOSAL and PAUSE for human
    confirm-create — the workflow NEVER creates or publishes a job itself.

    JD fields come from the node config (``data.jd_fields``) or the trigger/context
    (e.g. a ``file_uploaded`` trigger that already ran the JD extraction cascade).
    Decision ``awaiting_human_review`` halts the flow; a partner confirms creation
    via the existing draft-create endpoint (``POST /jobs``).
    """

    data = node.get("data", {})
    jd_fields = (
        data.get("jd_fields")
        or context.variables.get("jd_fields")
        or context.trigger.get("jd_fields")
    )
    proposal = _normalize_draft_proposal(jd_fields)
    if proposal is None:
        return NodeOutcome("not_computable", {"draft_reason": "no_jd_fields"})
    return NodeOutcome("awaiting_human_review", {"job_draft_proposal": proposal})
