"""Student offer comparison + on-demand negotiation guidance (WS-15 / Task N).

Two owner-only student reads on top of the ADR-0007 offer engine:

- :func:`compare_offers` — a DETERMINISTIC, FREE side-by-side of the student's own
  student-visible offers (position, company, their own disclosed comp, response
  deadline, status) enriched with the INTERNAL curated salary benchmark for each
  role. No AI, no external data, no energy.

- :func:`negotiation_guidance` — an ON-DEMAND, confirmation-gated, energy-metered
  AI narrative that helps the student reason about negotiating, grounded strictly
  in the deterministic comparison above (the same internal salary benchmark). It
  NEVER guarantees an outcome, degrades to deterministic tips when the AI gate is
  off or weekly energy is exhausted, and never exposes provider/model/token/prompt
  internals. The energy charge is idempotent per offer-set and only lands on a
  successful, user-visible narrative.

RBAC: owner-only. A student sees only its OWN offers (``applications.applicant_id
== principal.user_id``); a non-owner / unauthenticated caller is indistinguishable
from having no offers (never another student's comp). Salary is Fernet-decrypted
only for the owning student (DATA_MODEL §17) and never leaves the student surface.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.career import salary_benchmark
from app.ai.cv.llm import generate_note
from app.ai.energy import service as energy_service
from app.ai.energy.constants import FEATURE_OFFER_NEGOTIATION
from app.ai.gateway.factory import real_provider_active
from app.ai.observability.billable_usage import record_billable_usage
from app.ai.prompts.offer_negotiation import v1 as negotiation_prompt
from app.modules.auth.application.context import RequestContext
from app.modules.opportunities.application import job_read_facade
from app.modules.recruitment.application import _shared
from app.modules.recruitment.application.errors import ConfirmationRequiredError
from app.modules.recruitment.domain import offer as offer_domain
from app.modules.recruitment.domain.models import Application, Offer
from app.modules.recruitment.infrastructure.offer_salary_crypto import decrypt_salary
from app.shared.audit import write_audit
from app.shared.exceptions import AIUnavailableError, QuotaExceededError
from app.shared.permissions import Principal

logger = logging.getLogger(__name__)

_TASK_TYPE = "offer_negotiation"
_MAX_TOKENS = 320
_DEFAULT_LOCALE = "vi"

# The disclaimer is ALWAYS attached (AI on or off) so the product never implies a
# guaranteed negotiation result. Localized server-side (frontend renders raw).
_DISCLAIMER: dict[str, str] = {
    "vi": (
        "Đây là gợi ý tham khảo dựa trên dữ liệu thị trường nội bộ — không đảm bảo "
        "kết quả thương lượng. Hãy cân nhắc tổng thu nhập, sự phù hợp và cơ hội phát "
        "triển, và luôn giữ thái độ chuyên nghiệp, tôn trọng."
    ),
    "en": (
        "This is reference guidance based on internal market data — it does not "
        "guarantee any negotiation outcome. Weigh total compensation, fit, and growth, "
        "and always stay professional and respectful."
    ),
}

_TIPS: dict[str, list[str]] = {
    "vi": [
        "Nghiên cứu khoảng lương thị trường cho vai trò trước khi phản hồi.",
        "Xem xét toàn bộ gói đãi ngộ (thưởng, phúc lợi, cơ hội học hỏi), không chỉ "
        "lương cơ bản.",
        "Nếu đề nghị đối chiếu với thị trường, hãy nêu con số kỳ vọng một cách lịch "
        "sự và có căn cứ.",
        "Tôn trọng thời hạn phản hồi của thư mời và giữ liên lạc chuyên nghiệp.",
    ],
    "en": [
        "Research the market range for the role before you respond.",
        "Weigh the full package (bonus, benefits, learning) — not only base salary.",
        "If you counter, state your expectation politely and back it with evidence.",
        "Respect the offer's response deadline and keep communication professional.",
    ],
}


def _t(table: dict[str, str], locale: str) -> str:
    return table.get(locale, table[_DEFAULT_LOCALE])


def _tips(locale: str) -> list[str]:
    return _TIPS.get(locale, _TIPS[_DEFAULT_LOCALE])


# --------------------------------------------------------------------------- #
# Deterministic benchmark grounding                                            #
# --------------------------------------------------------------------------- #


def _benchmark_for(offer: Offer) -> dict:
    """Resolve the internal salary benchmark block for one offer's role.

    Returns ``{found, ...}``. Never fabricates a range: an unknown role returns
    ``{"found": False}`` so the narrative degrades to "not in benchmark".
    ``position_vs_market`` is only asserted when the offer comp is directly
    comparable (disclosed, VND, monthly) — otherwise ``None`` (honest).
    """

    matched = salary_benchmark.lookup(offer.position_title or "")
    if matched is None:
        return {"found": False}
    _key, data = matched
    tiers = data["tiers"]
    overall_min = min(t["min"] for t in tiers)
    overall_max = max(t["max"] for t in tiers)
    currency = data["currency"]

    position_vs_market: str | None = None
    amount = _decrypt_amount(offer)
    if (
        amount is not None
        and (offer.salary_currency or "").upper() == "VND"
        and (offer.salary_period or "") == offer_domain.DEFAULT_PERIOD
    ):
        offer_millions = amount / 1_000_000
        if offer_millions < overall_min:
            position_vs_market = "below_market"
        elif offer_millions > overall_max:
            position_vs_market = "above_market"
        else:
            position_vs_market = "within_market"

    return {
        "found": True,
        "market_band": f"{overall_min}–{overall_max}",
        "market_min": overall_min,
        "market_max": overall_max,
        "currency": currency,
        "tiers": tiers,
        "position_vs_market": position_vs_market,
    }


def _decrypt_amount(offer: Offer) -> int | None:
    raw = decrypt_salary(offer.salary_amount)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _comp_summary(offer: Offer) -> str | None:
    amount = _decrypt_amount(offer)
    if amount is None:
        return None
    period = offer_domain.period_label(offer.salary_period, locale=_DEFAULT_LOCALE)
    return f"{amount:,} {offer.salary_currency}/{period}"


# --------------------------------------------------------------------------- #
# Owner-scoped offer load                                                       #
# --------------------------------------------------------------------------- #


async def _student_offers(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[tuple[Offer, uuid.UUID]]:
    """Load the student's own student-visible offers with their job id (owner-only)."""

    rows = (
        await session.execute(
            select(Offer, Application.job_id)
            .join(Application, Offer.application_id == Application.id)
            .where(
                Application.applicant_id == user_id,
                Application.deleted_at.is_(None),
                Offer.status.in_(tuple(offer_domain.STUDENT_VISIBLE_STATUSES)),
            )
            .order_by(Offer.created_at.desc())
        )
    ).all()
    return [(row[0], row[1]) for row in rows]


async def _comparison_rows(
    session: AsyncSession, *, offers: list[tuple[Offer, uuid.UUID]], locale: str
) -> list[dict]:
    job_ids = [job_id for _o, job_id in offers]
    titles = await job_read_facade.get_job_titles(session, job_ids)

    rows: list[dict] = []
    for offer, job_id in offers:
        company_name = await _shared.org_display_name(session, offer.org_id)
        rows.append(
            {
                "id": str(offer.id),
                "application_id": str(offer.application_id),
                "position_title": offer.position_title,
                "company_name": company_name,
                "job_title": titles.get(job_id),
                "status": offer.status,
                "status_label": offer_domain.status_label(offer.status, locale=locale),
                # Owner-only decrypted comp (DATA_MODEL §17). ``None`` when the
                # partner did not disclose a figure.
                "salary_amount": _decrypt_amount(offer),
                "salary_currency": offer.salary_currency,
                "salary_period": offer.salary_period,
                "comp_summary": _comp_summary(offer),
                "expiry_date": _shared.as_aware(offer.expiry_date).isoformat(),
                "start_date": (
                    offer.start_date.isoformat() if offer.start_date else None
                ),
                "benchmark": _benchmark_for(offer),
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Deterministic comparison (free)                                              #
# --------------------------------------------------------------------------- #


async def compare_offers(
    session: AsyncSession,
    *,
    principal: Principal,
    locale: str = _DEFAULT_LOCALE,
) -> dict:
    """Deterministic side-by-side of the student's own offers (FREE, no AI).

    Owner-only: an unauthenticated caller simply has no offers. ``comparable`` is
    ``True`` once there are at least two offers to weigh against each other.
    """

    if not principal.is_authenticated or principal.user_id is None:
        return {"count": 0, "comparable": False, "offers": []}

    offers = await _student_offers(session, user_id=principal.user_id)
    rows = await _comparison_rows(session, offers=offers, locale=locale)
    return {
        "count": len(rows),
        "comparable": len(rows) >= 2,
        "offers": rows,
    }


# --------------------------------------------------------------------------- #
# On-demand negotiation guidance (confirmation-gated, energy-metered)          #
# --------------------------------------------------------------------------- #


async def _charge_negotiation_energy(
    session: AsyncSession, *, principal: Principal, offer_ids: tuple[str, ...]
) -> None:
    """Debit the student's AI energy for one freshly-generated narrative.

    Idempotent on the sorted offer-id set so re-requesting guidance for the same
    unchanged offers never double-charges. Best-effort; never breaks the read.
    Stores no provider/model/token internals.
    """

    try:
        ctx = energy_service.build_usage_context(
            principal,
            feature_key=FEATURE_OFFER_NEGOTIATION,
            task_type=_TASK_TYPE,
            resource_type="offer_set",
            idempotency_parts=offer_ids,
        )
        await record_billable_usage(
            session,
            ctx=ctx,
            result_status="success",
            base_units=energy_service.charge_units(FEATURE_OFFER_NEGOTIATION),
        )
    except Exception:  # noqa: BLE001 — accounting must never break the narrative
        logger.warning("offer_negotiation_energy_charge_failed", exc_info=True)


def _fallback_payload(rows: list[dict], *, locale: str, reason: str) -> dict:
    """Deterministic, free guidance payload (AI off / exhausted / unavailable)."""

    return {
        "offers": rows,
        "guidance": None,
        "ai_available": False,
        "ai_unavailable_reason": reason,
        "tips": _tips(locale),
        "disclaimer": _t(_DISCLAIMER, locale),
    }


async def negotiation_guidance(
    session: AsyncSession,
    *,
    principal: Principal,
    confirm: bool,
    ctx: RequestContext,
    locale: str = _DEFAULT_LOCALE,
) -> dict:
    """On-demand, metered AI negotiation narrative grounded in the comparison.

    ``confirm`` must be ``True`` (the explicit user consent for a metered AI write
    action, §4.3) — the router raises the user-safe confirmation error otherwise.
    Returns the deterministic comparison + tips + disclaimer always; ``guidance``
    is the advisory paragraph, ``None`` when there are no offers, the AI gate is
    off, weekly energy is exhausted, or the provider fails. Never raises for
    AI-off/failure; never guarantees an outcome; never leaks provider/model/token.
    """

    # Explicit consent gate for a metered AI write action (§4.3) — enforced in the
    # service, not the router. Checked BEFORE any offer load / model spend.
    if not confirm:
        raise ConfirmationRequiredError()

    if not principal.is_authenticated or principal.user_id is None:
        return _fallback_payload([], locale=locale, reason="no_offers")

    offers = await _student_offers(session, user_id=principal.user_id)
    rows = await _comparison_rows(session, offers=offers, locale=locale)
    if not rows:
        return _fallback_payload([], locale=locale, reason="no_offers")

    # AI gate OFF (default offline provider) -> deterministic tips only, no charge.
    if not real_provider_active():
        return _fallback_payload(rows, locale=locale, reason="ai_disabled")

    # Preflight the weekly energy gate; the narrative is advisory enrichment, so
    # degrade to tips-only on exhaustion rather than surfacing a 409.
    try:
        await energy_service.enforce_energy(session, principal=principal)
    except QuotaExceededError:
        return _fallback_payload(rows, locale=locale, reason="energy_exhausted")

    # Generate via the no-db (log-only) path so the runner does not auto-charge;
    # the charge is recorded explicitly + idempotently below on success only.
    try:
        text_out = await generate_note(
            task_type=_TASK_TYPE,
            system_prompt=negotiation_prompt.system_prompt(locale=locale),
            user_content=negotiation_prompt.build_user_content(offers=rows),
            temperature=0.3,
            max_tokens=_MAX_TOKENS,
        )
    except AIUnavailableError:
        return _fallback_payload(rows, locale=locale, reason="ai_unavailable")

    text_out = (text_out or "").strip()
    if not text_out:
        return _fallback_payload(rows, locale=locale, reason="ai_unavailable")

    offer_ids = tuple(sorted(r["id"] for r in rows))
    await _charge_negotiation_energy(
        session, principal=principal, offer_ids=offer_ids
    )
    await write_audit(
        session,
        action="offer.negotiation_guidance",
        resource_type="user",
        resource_id=principal.user_id,
        context=_shared.audit_ctx(principal, ctx),
        # PII-safe: counts only — never comp figures, company names, or narrative.
        after={"offer_count": len(rows), "ai_available": True},
    )
    await session.commit()

    return {
        "offers": rows,
        "guidance": text_out,
        "ai_available": True,
        "ai_unavailable_reason": None,
        "tips": _tips(locale),
        "disclaimer": _t(_DISCLAIMER, locale),
    }
