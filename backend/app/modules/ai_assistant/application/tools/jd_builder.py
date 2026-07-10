"""Conversational JD builder tools: structure pasted JD text + validate a draft.

Two read-only, human-in-the-loop tools that complete the JD authoring belt
(alongside ``draft_job_from_attachment`` / ``draft_job_description`` /
``create_job``):

- ``draft_job_from_text`` — the recruiter PASTES a JD (vi/en/mixed, may carry
  e-mail noise). Reuses the existing gateway-based JD extraction path
  (``jd_upload_service`` → is-JD gate → text-LLM structuring; no provider SDK is
  ever called here) and returns a normalized DRAFT. Non-JD/blank text is
  rejected user-safely — never fabricated into a job.
- ``validate_job_draft`` — DETERMINISTIC (no LLM) validation of the
  slot-filling state: required fields, salary/experience sanity, recommended
  completeness, bias scan. Powers the model's "what's still missing?" loop.

FROZEN artifact contract (the frontend builds against this exactly; also
returned by ``draft_job_from_attachment`` and ``draft_job_description``)::

    {"kind": "job_draft",
     "draft": {<_DRAFT_FIELDS subset present>},
     "missing_required": ["field", ...],
     "warnings": [{"code": str, "message": str}],   # message localized (vi)
     "ready": bool}

The model receives the same draft/missing/warnings JSON (minus ``render``) so
it can keep slot-filling conversationally, then calls ``create_job``
(confirmation-required) when the recruiter asks to save.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.opportunities.domain import lifecycle
from app.shared.exceptions import ValidationFailedError
from app.shared.permissions import Principal

# Canonical job-draft field set shared by every JD tool (kept in sync with
# ``jd_jobs._DRAFT_FIELDS`` — jd_jobs re-exports this tuple).
DRAFT_FIELDS = (
    "title",
    "description",
    "requirements",
    "benefits",
    "employment_type",
    "location_type",
    "location_city",
    "required_skills",
    "preferred_skills",
    "experience_min_years",
    "experience_max_years",
    "seniority_level",
    "salary_min",
    "salary_max",
    "salary_currency",
)

MAX_JD_TEXT_CHARS = 20_000

_REQUIRED_FIELDS = ("title", "description", "employment_type")
_KNOWN_CURRENCIES = frozenset({"VND", "USD", "EUR", "GBP", "JPY", "SGD", "AUD", "KRW", "CNY"})
_MIN_DESCRIPTION_CHARS = 200
_MIN_REQUIRED_SKILLS = 3
_MAX_EXPERIENCE_YEARS = 50

# Warning codes that keep ``ready`` False (structurally invalid values). The
# remaining codes are advisory completeness/quality nudges.
_BLOCKING_WARNING_CODES = frozenset(
    {
        "employment_type_invalid",
        "location_type_invalid",
        "seniority_level_invalid",
        "salary_range_invalid",
        "salary_currency_unknown",
        "experience_range_invalid",
    }
)

_WARNING_MESSAGES_VI: dict[str, str] = {
    "employment_type_invalid": (
        "Loại hình công việc không hợp lệ — chọn full_time, part_time, internship "
        "hoặc contract."
    ),
    "location_type_invalid": (
        "Hình thức làm việc không hợp lệ — chọn onsite, remote hoặc hybrid."
    ),
    "seniority_level_invalid": "Cấp bậc không hợp lệ — hãy chọn một cấp bậc trong danh mục.",
    "salary_range_invalid": "Mức lương tối thiểu đang lớn hơn mức lương tối đa.",
    "salary_currency_unknown": "Đơn vị tiền tệ không được hỗ trợ (ví dụ hợp lệ: VND, USD).",
    "experience_range_invalid": "Khoảng số năm kinh nghiệm không hợp lệ.",
    "missing_location": "Nên bổ sung địa điểm làm việc (thành phố hoặc chọn remote).",
    "few_required_skills": "Nên liệt kê ít nhất 3 kỹ năng bắt buộc để lọc ứng viên tốt hơn.",
    "description_short": "Mô tả công việc còn ngắn — nên viết tối thiểu 200 ký tự.",
    "bias_language": (
        "Phát hiện ngôn ngữ có thể mang tính phân biệt trong mô tả — hãy rà soát "
        "và chỉnh sửa trước khi đăng."
    ),
}


def _warning(code: str) -> dict:
    return {"code": code, "message": _WARNING_MESSAGES_VI.get(code, code)}


def _as_skill_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()][:30]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()][:30]
    return []


def _as_int(value: object) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def normalize_draft_fields(source: dict) -> dict:
    """Lift + type-coerce the DRAFT_FIELDS subset, DROPPING invalid enum values.

    Used on extraction output (an invalid extracted enum silently degrades to
    "missing" so the model asks the recruiter instead of persisting junk).
    """

    draft: dict = {}
    for k in DRAFT_FIELDS:
        v = source.get(k)
        if v in (None, "", [], {}):
            continue
        if k in ("required_skills", "preferred_skills"):
            v = _as_skill_list(v)
            if not v:
                continue
        elif k in ("experience_min_years", "experience_max_years", "salary_min", "salary_max"):
            v = _as_int(v)
            if v is None:
                continue
        elif k == "employment_type" and v not in lifecycle.EMPLOYMENT_TYPES:
            continue
        elif k == "location_type" and v not in lifecycle.LOCATION_TYPES:
            continue
        elif k == "seniority_level" and v not in lifecycle.SENIORITY_LEVELS:
            continue
        draft[k] = v
    return draft


def coerce_draft_input(source: dict) -> dict:
    """Lift + type-coerce the DRAFT_FIELDS subset, KEEPING invalid enum values.

    Used on recruiter/model-supplied drafts (``validate_job_draft``) so an
    invalid value is reported as a warning instead of silently vanishing.
    """

    draft: dict = {}
    for k in DRAFT_FIELDS:
        v = source.get(k)
        if v in (None, "", [], {}):
            continue
        if k in ("required_skills", "preferred_skills"):
            v = _as_skill_list(v)
            if not v:
                continue
        elif k in ("experience_min_years", "experience_max_years", "salary_min", "salary_max"):
            coerced = _as_int(v)
            if coerced is None:
                continue
            v = coerced
        elif k in ("title", "description", "requirements", "benefits", "location_city"):
            v = str(v).strip()
            if not v:
                continue
        else:
            v = str(v).strip()
            if not v:
                continue
        draft[k] = v
    return draft


def evaluate_draft(draft: dict) -> tuple[list[str], list[dict], bool]:
    """Deterministic draft validation: ``(missing_required, warnings, ready)``.

    No LLM call. ``ready`` = every required field present AND no structurally
    invalid value; advisory warnings (location/skills/length/bias) never block.
    """

    missing_required = [f for f in _REQUIRED_FIELDS if not draft.get(f)]
    warnings: list[dict] = []

    et = draft.get("employment_type")
    if et and et not in lifecycle.EMPLOYMENT_TYPES:
        warnings.append(_warning("employment_type_invalid"))
    lt = draft.get("location_type")
    if lt and lt not in lifecycle.LOCATION_TYPES:
        warnings.append(_warning("location_type_invalid"))
    seniority = draft.get("seniority_level")
    if seniority and seniority not in lifecycle.SENIORITY_LEVELS:
        warnings.append(_warning("seniority_level_invalid"))

    smin, smax = draft.get("salary_min"), draft.get("salary_max")
    if (
        isinstance(smin, int)
        and isinstance(smax, int)
        and smin > smax
    ) or (isinstance(smin, int) and smin < 0) or (isinstance(smax, int) and smax < 0):
        warnings.append(_warning("salary_range_invalid"))
    currency = draft.get("salary_currency")
    if currency and str(currency).upper() not in _KNOWN_CURRENCIES:
        warnings.append(_warning("salary_currency_unknown"))

    emin, emax = draft.get("experience_min_years"), draft.get("experience_max_years")
    exp_invalid = False
    for v in (emin, emax):
        if isinstance(v, int) and not (0 <= v <= _MAX_EXPERIENCE_YEARS):
            exp_invalid = True
    if isinstance(emin, int) and isinstance(emax, int) and emin > emax:
        exp_invalid = True
    if exp_invalid:
        warnings.append(_warning("experience_range_invalid"))

    if not draft.get("location_city") and draft.get("location_type") != "remote":
        warnings.append(_warning("missing_location"))
    if len(draft.get("required_skills") or []) < _MIN_REQUIRED_SKILLS:
        warnings.append(_warning("few_required_skills"))
    description = str(draft.get("description") or "")
    if description and len(description) < _MIN_DESCRIPTION_CHARS:
        warnings.append(_warning("description_short"))

    if description:
        try:
            from app.ai.safety.bias_detection import check_bias

            if check_bias(description[:6000]).flagged:
                warnings.append(_warning("bias_language"))
        except Exception:  # noqa: BLE001 - the scan is best-effort, never fatal
            pass

    codes = {w["code"] for w in warnings}
    ready = not missing_required and not (codes & _BLOCKING_WARNING_CODES)
    return missing_required, warnings, ready


def job_draft_result(draft: dict, *, note: str | None = None, **extra: object) -> dict:
    """The shared success payload + FROZEN ``job_draft`` render artifact."""

    missing_required, warnings, ready = evaluate_draft(draft)
    result: dict = {
        "ok": True,
        "draft": draft,
        "missing_required": missing_required,
        "warnings": warnings,
        "ready": ready,
        # FE-only render artifact (stripped before the model sees the result).
        "render": {
            "kind": "job_draft",
            "draft": draft,
            "missing_required": missing_required,
            "warnings": warnings,
            "ready": ready,
        },
    }
    if note:
        result["note"] = note
    result.update(extra)
    return result


# --------------------------------------------------------------------------- #
# Extraction seam (monkeypatchable in tests; offline → ai_unavailable)         #
# --------------------------------------------------------------------------- #


async def _run_extraction(jd_text: str) -> dict:
    """Route pasted text through the SAME gateway-based JD cascade as uploads.

    Wrapping the text as a ``.txt`` upload reuses the whole pipeline verbatim:
    is-JD gate → text-LLM structuring (via the AI gateway) → validate + score.
    No provider SDK is called here.
    """

    from app.modules.opportunities.application import jd_upload_service

    return await jd_upload_service.extract_jd_from_upload(
        "pasted-jd.txt", jd_text.encode("utf-8")
    )


# --------------------------------------------------------------------------- #
# Tools                                                                        #
# --------------------------------------------------------------------------- #


async def draft_job_from_text(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Structure a PASTED JD into a job draft (never persists anything)."""

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    jd_text = str(args.get("jd_text") or "").strip()
    if not jd_text:
        return {"ok": False, "error": "jd_text_required"}
    if len(jd_text) > MAX_JD_TEXT_CHARS:
        return {"ok": False, "error": "jd_text_too_long"}

    target_language = str(args.get("target_language") or "").strip().lower()
    if target_language not in ("vi", "en"):
        target_language = ""

    try:
        jd = await _run_extraction(jd_text)
    except ValidationFailedError:
        # blank / not-a-JD / junk — user-safe, never fabricated into a job.
        return {"ok": False, "error": "not_a_jd"}
    except Exception:
        return {"ok": False, "error": "extract_failed"}

    if jd.get("status") == "ai_unavailable":
        return {"ok": False, "error": "ai_unavailable"}

    draft = normalize_draft_fields(jd)
    note = (
        "Draft structured from the pasted JD — nothing saved yet. Fill the "
        "missing_required fields with the recruiter conversationally, re-check "
        "with validate_job_draft, then call create_job when they confirm."
    )
    extra: dict = {"needs_review": bool(jd.get("needs_review", False))}
    if target_language:
        extra["target_language"] = target_language
    return job_draft_result(draft, note=note, **extra)


async def validate_job_draft(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Deterministic slot-filling validation of a job draft (no LLM, no writes)."""

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    draft = coerce_draft_input(args)
    note = (
        "Deterministic check only — nothing saved. ready=true means the draft "
        "meets the minimum posting bar; advisory warnings should still be "
        "reviewed with the recruiter before create_job."
    )
    return job_draft_result(draft, note=note)
