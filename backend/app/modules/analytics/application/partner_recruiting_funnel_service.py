"""Partner recruiting-funnel analytics read (design spec §6 "Analytics" surface).

Unifies the coarse ``applications.status`` outcome with the fine
``candidate_stages`` pipeline position into the classic recruiting funnel
(applied -> screened -> interview -> offer -> hired), plus per-stage conversion
(from ``candidate_stages.exit_kind``), time-to-hire (applied -> hired), and
time-in-stage (entered -> exited) medians with bucketed distributions.

RBAC is enforced HERE (service layer): the caller must be a partner-org member
holding ``analytics:view_job_metrics`` for their own org. The raw, RBAC-free
aggregation lives in ``recruitment.application.dashboard_read`` (that module's
documented contract is "the calling application service owns the persona gate").

No PII, no other-candidate detail, no raw model/provider internals — only
org-scoped aggregate counts and bucketed durations. Sparse metrics report
``low_signal: true`` (never a fabricated confident median).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.domain import personas
from app.modules.recruitment.application import dashboard_read as recruitment_read
from app.shared.exceptions import AuthRequiredError, PermissionDeniedError, ResourceNotFoundError
from app.shared.permissions import Principal, permission_checker

# A median computed from fewer than this many samples is flagged ``low_signal``
# so the UI shows an honest "not enough data yet" state instead of a confident
# single-point "median".
_MIN_SIGNAL = 5

# Ordered funnel steps + their localized labels.
_FUNNEL_ORDER: tuple[str, ...] = ("applied", "screened", "interview", "offer", "hired")
_FUNNEL_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "applied": "Ứng tuyển",
        "screened": "Sàng lọc",
        "interview": "Phỏng vấn",
        "offer": "Đề nghị",
        "hired": "Tuyển dụng",
    },
    "en": {
        "applied": "Applied",
        "screened": "Screened",
        "interview": "Interview",
        "offer": "Offer",
        "hired": "Hired",
    },
}

_STAGE_TYPE_LABELS: dict[str, dict[str, str]] = {
    "vi": {
        "screening": "Sàng lọc hồ sơ",
        "interview": "Phỏng vấn",
        "assessment": "Đánh giá",
        "offer": "Đề nghị",
        "custom": "Khác",
    },
    "en": {
        "screening": "Screening",
        "interview": "Interview",
        "assessment": "Assessment",
        "offer": "Offer",
        "custom": "Custom",
    },
}

# Day-duration histogram buckets: [lo, hi) in days (hi=None is the open top bin).
_DAY_BUCKETS: tuple[tuple[str, float, float | None], ...] = (
    ("lt_1d", 0.0, 1.0),
    ("1_3d", 1.0, 3.0),
    ("3_7d", 3.0, 7.0),
    ("1_2w", 7.0, 14.0),
    ("2_4w", 14.0, 30.0),
    ("gt_4w", 30.0, None),
)


def _locale(locale: str) -> str:
    return locale if locale in _FUNNEL_LABELS else "vi"


def _funnel_label(stage: str, locale: str) -> str:
    return _FUNNEL_LABELS[_locale(locale)].get(stage, stage)


def _stage_type_label(stage_type: str, locale: str) -> str:
    return _STAGE_TYPE_LABELS[_locale(locale)].get(stage_type, stage_type)


def _require_partner_analytics(principal: Principal) -> uuid.UUID:
    """Authenticated partner member holding ``analytics:view_job_metrics``."""

    if not principal.is_authenticated:
        raise AuthRequiredError()
    if principal.persona != personas.PARTNER_MEMBER:
        raise PermissionDeniedError()
    if principal.org_id is None:
        raise ResourceNotFoundError()
    permission_checker.require(
        principal, "analytics", "view_job_metrics", resource_org_id=principal.org_id
    )
    return principal.org_id


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return round(ordered[mid], 1)
    return round((ordered[mid - 1] + ordered[mid]) / 2.0, 1)


def _bucketize(values: list[float]) -> list[dict]:
    counts = {key: 0 for key, _, _ in _DAY_BUCKETS}
    for v in values:
        for key, lo, hi in _DAY_BUCKETS:
            if v >= lo and (hi is None or v < hi):
                counts[key] += 1
                break
    return [{"key": key, "count": counts[key]} for key, _, _ in _DAY_BUCKETS]


def _duration_block(values: list[float]) -> dict:
    sample_size = len(values)
    return {
        "sample_size": sample_size,
        "median_days": _median(values),
        "low_signal": sample_size < _MIN_SIGNAL,
        "buckets": _bucketize(values),
    }


def _build_funnel(counts: dict[str, int], locale: str) -> list[dict]:
    funnel: list[dict] = []
    prev: int | None = None
    for stage in _FUNNEL_ORDER:
        count = int(counts.get(stage, 0))
        conversion = round((count / prev) * 100.0, 1) if prev else None
        funnel.append(
            {
                "stage": stage,
                "label": _funnel_label(stage, locale),
                "count": count,
                "conversion_from_prev_pct": conversion,
            }
        )
        prev = count
    return funnel


def _build_stage_outcomes(rows: list[dict], locale: str) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        entered = int(row.get("entered", 0))
        advanced = int(row.get("advanced", 0))
        pass_rate = round((advanced / entered) * 100.0, 1) if entered else None
        out.append(
            {
                "stage_type": row["stage_type"],
                "label": _stage_type_label(row["stage_type"], locale),
                "entered": entered,
                "advanced": advanced,
                "rejected": int(row.get("rejected", 0)),
                "rolled_back": int(row.get("rolled_back", 0)),
                "active": int(row.get("active", 0)),
                "pass_rate_pct": pass_rate,
            }
        )
    return out


async def get_recruiting_funnel(
    session: AsyncSession, *, principal: Principal, locale: str = "vi"
) -> dict:
    """Assemble the funnel + conversion + time-to-hire + time-in-stage read model."""

    org_id = _require_partner_analytics(principal)

    counts = await recruitment_read.recruiting_funnel_counts(session, org_id=org_id)
    exit_rows = await recruitment_read.stage_exit_breakdown(session, org_id=org_id)
    tth_samples = await recruitment_read.time_to_hire_samples(session, org_id=org_id)
    tis_samples = await recruitment_read.time_in_stage_samples(session, org_id=org_id)

    time_in_stage = [
        {
            "stage_type": stage_type,
            "label": _stage_type_label(stage_type, locale),
            **_duration_block(samples),
        }
        for stage_type, samples in sorted(tis_samples.items())
    ]

    return {
        "funnel": _build_funnel(counts, locale),
        "stage_outcomes": _build_stage_outcomes(exit_rows, locale),
        "time_to_hire": _duration_block(tth_samples),
        "time_in_stage": time_in_stage,
    }
