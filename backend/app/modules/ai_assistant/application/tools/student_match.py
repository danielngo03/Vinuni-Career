"""Student CV↔job matching tool handlers (system-data-only render cards).

Five read-only student tools that turn the caller's OWN CVs + the platform's
visible jobs into beautiful in-chat cards using ONLY internal system data and the
deterministic CV-JD scorer (``app.ai.cv.job_fit``) — no external calls, no image
generation, no model spend for the number. Each attaches a FROZEN ``render``
artifact (schemas: ``docs/superpowers/specs/2026-07-11-student-ai-power-design.md``
§3) that ``native_loop`` pops out of the model context before the result
re-enters the model, exactly like the partner ``render`` block.

Everything is scoped to the caller via ``principal``: CVs come from the owner-only
``cv_ranking_facade`` / ``cv_service`` reads, and jobs come from the persona-gated
``job_fit_read`` visibility filter, so student A can never read student B's CV or
score an invisible job. The user-facing fit is a 0-100 PRODUCT score + a
qualitative band KEY (``strong``/``good``/``fair``/``weak``) that the frontend
localizes and colors (colorblind-safe) — never a raw model confidence, provider,
model, token, or embedding internal.

Shared CV-resolution rule (all CV-consuming tools): when ``cv_id`` is omitted →
exactly 1 library CV is used silently; >1 returns ``needs_cv_selection`` + a
``cv_picker`` render (NO heavy CV data in the model-visible fields); 0 returns a
helpful ``ok:true`` message telling the student to create/upload a CV first.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv import grounding, job_fit
from app.shared.permissions import Principal

# Personas allowed to use the student match tools (alumni share the student
# journey; ``None`` never reaches here because the tools require authentication).
_STUDENT_PERSONAS = frozenset({"student", "alumni"})

# ``source_type`` codes stored on ``cv_profiles`` that mean an uploaded document
# (read-only, no builder editor) vs a template/builder CV.
_UPLOADED_SOURCES = frozenset({"uploaded_import"})

# Section-type buckets for the CV card facets (normalized, underscore form).
_EXPERIENCE_SECTIONS = frozenset({"experience", "work", "work_experience", "internship"})
_EDUCATION_SECTIONS = frozenset({"education"})
_SUMMARY_SECTIONS = frozenset({"summary", "objective"})

_MAX_CARD_SKILLS = 8
_DEFAULT_MATCH_LIMIT = 6
_MAX_MATCH_LIMIT = 10
_STALE_FALLBACK_DAYS = 180

# Friendly names for the 6 deterministic fit bands (job_fit.BandScores), used to
# turn band scores into short strength/gap phrases. Baked bilingually like the
# other chart/analytics tools (native_loop does not inject a locale into args).
_BAND_META: dict[str, dict[str, str]] = {
    "skills": {"vi": "Kỹ năng chuyên môn", "en": "Technical skills"},
    "experience": {"vi": "Kinh nghiệm liên quan", "en": "Relevant experience"},
    "scope": {"vi": "Phạm vi & tác động", "en": "Scope & impact"},
    "credentials": {"vi": "Bằng cấp & chứng chỉ", "en": "Education & credentials"},
    "soft_skills": {"vi": "Kỹ năng mềm", "en": "Soft skills"},
    "trajectory": {"vi": "Lộ trình nghề nghiệp", "en": "Career trajectory"},
}
_STRENGTH_FLOOR = 75  # band >= this reads as a strength
_GAP_CEILING = 45  # band <= this reads as a gap


# --------------------------------------------------------------------------- #
# Small pure helpers                                                          #
# --------------------------------------------------------------------------- #


def _loc(args: dict) -> str:
    return "en" if str(args.get("locale") or "vi").lower().startswith("en") else "vi"


def _uuid_or_none(raw: object) -> _uuid.UUID | None:
    if raw in (None, ""):
        return None
    try:
        return _uuid.UUID(str(raw).strip())
    except (ValueError, AttributeError):
        return None


def _band_key(score: int) -> str:
    """Qualitative fit band the FE localizes + colors. Mirrors the partner/
    application fit thresholds so a student and a recruiter read the same CV the
    same way."""
    if score >= 80:
        return "strong"
    if score >= 65:
        return "good"
    if score >= 50:
        return "fair"
    return "weak"


def _require_student(principal: Principal) -> dict | None:
    if not principal.is_authenticated:
        return {"ok": False, "error": "auth_required"}
    persona = getattr(principal, "persona", None)
    if persona is not None and persona not in _STUDENT_PERSONAS:
        return {"ok": False, "error": "student_only"}
    return None


def _norm_section_type(section: dict) -> str:
    return str(section.get("section_type") or "").strip().lower().replace(" ", "_")


def _salary_text(job: dict) -> str | None:
    """Compact salary display from the leak-safe projection (or ``None``)."""
    if not job.get("salary_is_disclosed"):
        return None
    lo = job.get("salary_min")
    hi = job.get("salary_max")
    cur = job.get("salary_currency") or "VND"
    if isinstance(lo, int) and isinstance(hi, int):
        return f"{lo:,}–{hi:,} {cur}"
    if isinstance(lo, int):
        return f"≥ {lo:,} {cur}"
    if isinstance(hi, int):
        return f"≤ {hi:,} {cur}"
    return None


def _facets(cv_input: job_fit.CvInput) -> tuple[list[dict], int, int, str | None]:
    """Extract (top_skills, experience_count, education_count, summary) for a card."""
    top_skills: list[dict] = []
    experience = 0
    education = 0
    summary: str | None = None
    for section in cv_input.sections:
        stype = _norm_section_type(section)
        content = section.get("content")
        content = content if isinstance(content, dict) else {}
        if "skill" in stype:
            items = content.get("items")
            if isinstance(items, list):
                for item in items:
                    if len(top_skills) >= _MAX_CARD_SKILLS:
                        break
                    if isinstance(item, str) and item.strip():
                        top_skills.append({"name": item.strip()[:60], "level": None})
                    elif isinstance(item, dict):
                        name = item.get("name") or item.get("label")
                        if not isinstance(name, str) or not name.strip():
                            continue
                        raw_level = item.get("level")
                        level = (
                            int(raw_level)
                            if isinstance(raw_level, int | float) and 0 <= raw_level <= 100
                            else None
                        )
                        top_skills.append({"name": name.strip()[:60], "level": level})
        elif stype in _EXPERIENCE_SECTIONS:
            entries = content.get("entries")
            if isinstance(entries, list):
                experience += sum(1 for e in entries if isinstance(e, dict))
        elif stype in _EDUCATION_SECTIONS:
            entries = content.get("entries")
            if isinstance(entries, list):
                education += sum(1 for e in entries if isinstance(e, dict))
        elif stype in _SUMMARY_SECTIONS and summary is None:
            text = grounding.content_to_text(content).strip()
            summary = text[:240] or None
    return top_skills, experience, education, summary


def _band_narrative(bands: job_fit.BandScores, locale: str) -> tuple[list[str], list[str]]:
    """Short strength/gap phrases from the 6 band scores (localized)."""
    scores = bands.as_dict()
    strengths = [
        _BAND_META[key][locale]
        for key, value in scores.items()
        if key in _BAND_META and value >= _STRENGTH_FLOOR
    ]
    gaps = [
        _BAND_META[key][locale]
        for key, value in scores.items()
        if key in _BAND_META and value <= _GAP_CEILING
    ]
    return strengths[:4], gaps[:4]


def _fit_suggestions(
    fit: job_fit.CvFit, cv_id: str, *, is_template: bool, locale: str
) -> list[dict]:
    """1-3 actionable suggestions; the CV-Studio hand-off is only offered for a
    template CV (uploaded CVs are read-only and have no builder editor)."""
    out: list[dict] = []
    gaps = [g for g in fit.gaps if g][:4]
    if gaps:
        joined = ", ".join(gaps)
        if locale == "en":
            text = f"Add evidence for these missing skills to your CV: {joined}."
        else:
            text = f"Bổ sung bằng chứng cho các kỹ năng còn thiếu vào CV: {joined}."
        out.append(
            {
                "text": text,
                "action": {"kind": "cv_studio", "cv_id": cv_id} if is_template else None,
            }
        )
    if fit.stale:
        out.append(
            {
                "text": (
                    "Refresh this CV — it hasn't been updated in a while."
                    if locale == "en"
                    else "Cập nhật lại CV này — đã khá lâu chưa chỉnh sửa."
                ),
                "action": {"kind": "cv_studio", "cv_id": cv_id} if is_template else None,
            }
        )
    out.append(
        {
            "text": (
                "Practice a mock interview to prepare for this role."
                if locale == "en"
                else "Luyện phỏng vấn thử để chuẩn bị cho vị trí này."
            ),
            "action": None,
        }
    )
    return out[:3]


# --------------------------------------------------------------------------- #
# CV library load + resolution                                                #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _LibCv:
    cv_id: str
    title: str
    source: str  # "uploaded" | "template"
    updated_at: str | None
    cv_input: job_fit.CvInput | None
    is_default: bool = False


async def _load_library(session: AsyncSession, principal: Principal) -> list[_LibCv]:
    """The caller's matchable library CVs (owner-scoped), newest-edited first.

    Joins the deterministic scoring inputs (``cv_ranking_facade`` — ready CVs only)
    with the CV summaries (title/source/updated_at). The most-recently-edited
    library CV is flagged ``is_default`` (there is no stored default-CV column, so
    this is the deterministic natural default).
    """
    from app.modules.documents.application import cv_ranking_facade, cv_service

    try:
        cv_inputs = await cv_ranking_facade.build_cv_inputs(session, principal=principal)
    except Exception:  # noqa: BLE001 - owner/permission failure → treat as no CVs
        cv_inputs = []
    inputs_by_id = {ci.cv_id: ci for ci in cv_inputs}

    try:
        summaries, _next, _limit = await cv_service.list_cvs(
            session, principal=principal, cursor=None, limit=50
        )
    except Exception:  # noqa: BLE001 - defensive; never surface a raw error
        summaries = []

    lib: list[_LibCv] = []
    for summary in summaries:
        if not summary.get("in_library"):
            continue
        cid = str(summary.get("id"))
        lib.append(
            _LibCv(
                cv_id=cid,
                title=summary.get("title") or "CV",
                source=(
                    "uploaded"
                    if summary.get("source_type") in _UPLOADED_SOURCES
                    else "template"
                ),
                updated_at=summary.get("last_edited_at") or summary.get("finalized_at"),
                cv_input=inputs_by_id.get(cid),
            )
        )
    lib.sort(key=lambda c: (c.updated_at or ""), reverse=True)
    if lib:
        lib[0].is_default = True
    return lib


def _picker_render(
    usable: list[_LibCv], *, pending_tool: str, pending_args: dict, prompt_key: str
) -> dict:
    return {
        "kind": "cv_picker",
        "prompt_key": prompt_key,
        "pending_tool": pending_tool,
        # The picker is re-issued WITH the chosen cv_id, so drop the omitted one.
        "pending_args": {k: v for k, v in pending_args.items() if k != "cv_id"},
        "cvs": [
            {
                "cv_id": c.cv_id,
                "title": c.title,
                "source": c.source,
                "updated_at": c.updated_at,
                "is_default": c.is_default,
            }
            for c in usable
        ],
    }


def _no_cv_result(locale: str) -> dict:
    return {
        "ok": True,
        "no_cv": True,
        "message": (
            "You don't have a CV in your library yet. Ask the student to create or "
            "upload a CV first (they can do this at /student/cvs)."
            if locale == "en"
            else "Bạn chưa có CV nào trong thư viện. Hãy hướng dẫn tạo hoặc tải lên "
            "một CV trước (tại /student/cvs)."
        ),
    }


def _resolve_cv(
    principal: Principal,
    cv_id_raw: object,
    *,
    lib: list[_LibCv],
    pending_tool: str,
    pending_args: dict,
    prompt_key: str,
    locale: str,
    allow_none: bool = False,
) -> tuple[_LibCv | None, dict | None]:
    """Shared CV-resolution rule. Returns ``(chosen, short_circuit_result)``.

    ``short_circuit_result`` is non-None when the tool must stop and return it
    directly (invalid id, needs-selection picker, or the no-CV message).
    ``allow_none`` (compare_jobs) lets 0 CVs fall through with ``(None, None)`` so
    the comparison still renders without a fit column.
    """
    usable = [c for c in lib if c.cv_input is not None]
    if cv_id_raw:
        cid = str(cv_id_raw).strip()
        if _uuid_or_none(cid) is None:
            return None, {"ok": False, "error": "invalid_cv_id"}
        match = next((c for c in usable if c.cv_id == cid), None)
        if match is None:
            return None, {"ok": False, "error": "cv_not_found"}
        return match, None

    if not usable:
        return (None, None) if allow_none else (None, _no_cv_result(locale))
    if len(usable) == 1:
        return usable[0], None
    return None, {
        "ok": True,
        "needs_cv_selection": True,
        "instruction": (
            f"Ask the user to choose which CV to use, then call `{pending_tool}` "
            "again with that cv_id. Do not guess a CV."
        ),
        "render": _picker_render(
            usable, pending_tool=pending_tool, pending_args=pending_args, prompt_key=prompt_key
        ),
    }


def _stale_days() -> int:
    try:
        from app.core.config import get_settings

        return int(get_settings().cv_stale_after_days)
    except Exception:  # noqa: BLE001 - config always present; belt-and-braces
        return _STALE_FALLBACK_DAYS


# --------------------------------------------------------------------------- #
# Tool 1: match_cv_to_jobs → job_match_list                                   #
# --------------------------------------------------------------------------- #


async def match_cv_to_jobs(session: AsyncSession, principal: Principal, args: dict) -> dict:
    err = _require_student(principal)
    if err:
        return err
    locale = _loc(args)
    lib = await _load_library(session, principal)
    chosen, short = _resolve_cv(
        principal,
        args.get("cv_id"),
        lib=lib,
        pending_tool="match_cv_to_jobs",
        pending_args=args,
        prompt_key="picker.chooseCvForMatch",
        locale=locale,
    )
    if short is not None:
        return short
    assert chosen is not None and chosen.cv_input is not None

    query = (args.get("query") or "").strip() or None
    location = (args.get("location") or "").strip() or None
    try:
        limit = int(args.get("limit") or _DEFAULT_MATCH_LIMIT)
    except (TypeError, ValueError):
        limit = _DEFAULT_MATCH_LIMIT
    limit = max(1, min(limit, _MAX_MATCH_LIMIT))

    from app.modules.opportunities.application import (
        job_fit_read,
        job_service,
        saved_jobs_service,
    )

    q = " ".join(p for p in (query, location) if p) or None
    try:
        items, _n, _l, _t = await job_service.list_public_jobs(
            session, principal=principal, q=q, cursor=None, limit=limit * 3, locale=locale
        )
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "tool_failed"}

    saved_ids = await saved_jobs_service.get_saved_ids(session, principal=principal)
    stale = _stale_days()
    persona = principal.persona or "student"

    scored: list[tuple[job_fit.CvFit, dict, dict, _uuid.UUID]] = []
    for item in items:
        jid = _uuid_or_none(item.get("id"))
        if jid is None:
            continue
        # ``load_job_for_fit`` has NO view-metric side effect (unlike get_job), so a
        # bulk match never inflates partner engagement counters.
        job = await job_fit_read.load_job_for_fit(
            session, job_id=jid, persona=persona, locale=locale
        )
        if job is None:
            continue
        outcome = job_fit.evaluate(job, [chosen.cv_input], stale_days=stale)
        if not outcome.results:
            continue
        scored.append((outcome.results[0], item, job, jid))

    scored.sort(key=lambda r: -r[0].score)
    top = scored[:limit]

    render_items: list[dict] = []
    for fit, item, job, jid in top:
        raw_company = item.get("company")
        company = raw_company if isinstance(raw_company, dict) else {}
        render_items.append(
            {
                "job_id": str(jid),
                "title": item.get("title") or job.get("title") or "",
                "company_name": company.get("display_name") or job.get("company_name"),
                "location": job.get("location_city") or _item_city(item),
                "fit_score": fit.score,
                "fit_band": _band_key(fit.score),
                "top_reasons": [m for m in fit.matched_skills if m][:3],
                "deadline": item.get("application_deadline") or job.get("application_deadline"),
                "is_saved": jid in saved_ids,
                "view_path": f"/jobs/{jid}",
            }
        )

    return {
        "ok": True,
        "cv_title": chosen.title,
        "match_count": len(render_items),
        # Compact model-visible summary; the full grid lives only in ``render``.
        "top": [{"title": r["title"], "fit_band": r["fit_band"]} for r in render_items[:5]],
        "render": {
            "kind": "job_match_list",
            "cv_id": chosen.cv_id,
            "cv_title": chosen.title,
            "total": len(render_items),
            "items": render_items,
        },
    }


def _item_city(item: dict) -> str | None:
    locations = item.get("locations")
    if isinstance(locations, list) and locations and isinstance(locations[0], dict):
        city = locations[0].get("city")
        if isinstance(city, str) and city.strip():
            return city
    hq = item.get("headquarters_city")
    return hq if isinstance(hq, str) and hq.strip() else None


# --------------------------------------------------------------------------- #
# Tool 2: explain_job_fit → fit_breakdown                                     #
# --------------------------------------------------------------------------- #


async def explain_job_fit(session: AsyncSession, principal: Principal, args: dict) -> dict:
    err = _require_student(principal)
    if err:
        return err
    locale = _loc(args)
    job_id = _uuid_or_none(args.get("job_id"))
    if job_id is None:
        return {"ok": False, "error": "invalid_job_id"}

    lib = await _load_library(session, principal)
    chosen, short = _resolve_cv(
        principal,
        args.get("cv_id"),
        lib=lib,
        pending_tool="explain_job_fit",
        pending_args=args,
        prompt_key="picker.chooseCvForFit",
        locale=locale,
    )
    if short is not None:
        return short
    assert chosen is not None and chosen.cv_input is not None

    from app.modules.opportunities.application import job_fit_read

    job = await job_fit_read.load_job_for_fit(
        session, job_id=job_id, persona=principal.persona or "student", locale=locale
    )
    if job is None:
        return {"ok": False, "error": "job_not_found"}

    outcome = job_fit.evaluate(job, [chosen.cv_input], stale_days=_stale_days())
    if not outcome.results:
        return {"ok": False, "error": "scoring_failed"}
    fit = outcome.results[0]

    req_keys = {grounding.normalize(x) for x in (job.get("required_skills") or [])}
    pref_keys = {grounding.normalize(x) for x in (job.get("preferred_skills") or [])}
    missing_skills: list[dict] = []
    for gap in [g for g in fit.gaps if g][:10]:
        key = grounding.normalize(gap)
        importance = "high" if key in req_keys else ("medium" if key in pref_keys else "low")
        missing_skills.append({"name": gap, "importance": importance})

    matched_skills = [{"name": m, "evidence": None} for m in fit.matched_skills if m][:10]
    strengths, gaps = _band_narrative(fit.bands, locale)
    suggestions = _fit_suggestions(
        fit, chosen.cv_id, is_template=(chosen.source == "template"), locale=locale
    )

    return {
        "ok": True,
        "job_title": job.get("title") or "",
        "fit_score": fit.score,
        "fit_band": _band_key(fit.score),
        "render": {
            "kind": "fit_breakdown",
            "job_id": str(job_id),
            "job_title": job.get("title") or "",
            "company_name": job.get("company_name"),
            "cv_id": chosen.cv_id,
            "cv_title": chosen.title,
            "fit_score": fit.score,
            "fit_band": _band_key(fit.score),
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "strengths": strengths,
            "gaps": gaps,
            "suggestions": suggestions,
        },
    }


# --------------------------------------------------------------------------- #
# Tool 3: compare_jobs → job_compare                                          #
# --------------------------------------------------------------------------- #


async def compare_jobs(session: AsyncSession, principal: Principal, args: dict) -> dict:
    err = _require_student(principal)
    if err:
        return err
    locale = _loc(args)

    raw_ids = args.get("job_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        return {"ok": False, "error": "job_ids_required"}
    ids: list[_uuid.UUID] = []
    for raw in raw_ids:
        parsed = _uuid_or_none(raw)
        if parsed is not None and parsed not in ids:
            ids.append(parsed)
    if not (2 <= len(ids) <= 4):
        return {"ok": False, "error": "need_2_to_4_jobs"}

    lib = await _load_library(session, principal)
    # CV is OPTIONAL for a compare — 0 CVs still renders (without a fit column).
    chosen, short = _resolve_cv(
        principal,
        args.get("cv_id"),
        lib=lib,
        pending_tool="compare_jobs",
        pending_args=args,
        prompt_key="picker.chooseCvForCompare",
        locale=locale,
        allow_none=True,
    )
    if short is not None:
        return short

    from app.modules.opportunities.application import job_fit_read

    stale = _stale_days()
    persona = principal.persona or "student"
    jobs_data: list[tuple[_uuid.UUID, dict, job_fit.CvFit | None]] = []
    for jid in ids:
        job = await job_fit_read.load_job_for_fit(
            session, job_id=jid, persona=persona, locale=locale
        )
        if job is None:
            continue
        fit: job_fit.CvFit | None = None
        if chosen is not None and chosen.cv_input is not None:
            outcome = job_fit.evaluate(job, [chosen.cv_input], stale_days=stale)
            fit = outcome.results[0] if outcome.results else None
        jobs_data.append((jid, job, fit))

    if len(jobs_data) < 2:
        return {"ok": False, "error": "jobs_not_found"}

    jobs = [
        {
            "job_id": str(jid),
            "title": job.get("title") or "",
            "company_name": job.get("company_name"),
            "view_path": f"/jobs/{jid}",
        }
        for jid, job, _ in jobs_data
    ]

    rows: list[dict] = []
    if chosen is not None:
        rows.append(
            {
                "label_key": "fit",
                "values": [(_band_key(f.score) if f else None) for _, _, f in jobs_data],
            }
        )
        rows.append(
            {
                "label_key": "fit_score",
                "values": [(f.score if f else None) for _, _, f in jobs_data],
            }
        )
        rows.append(
            {
                "label_key": "skills_matched",
                "values": [
                    (len([m for m in f.matched_skills if m]) if f else None)
                    for _, _, f in jobs_data
                ],
            }
        )
    rows.append(
        {"label_key": "salary", "values": [_salary_text(job) for _, job, _ in jobs_data]}
    )
    rows.append(
        {
            "label_key": "location",
            "values": [job.get("location_city") for _, job, _ in jobs_data],
        }
    )
    rows.append(
        {
            "label_key": "mode",
            "values": [job.get("location_type_label") for _, job, _ in jobs_data],
        }
    )
    rows.append(
        {
            "label_key": "employment_type",
            "values": [job.get("employment_type_label") for _, job, _ in jobs_data],
        }
    )
    rows.append(
        {
            "label_key": "seniority",
            "values": [job.get("seniority_level") for _, job, _ in jobs_data],
        }
    )
    rows.append(
        {
            "label_key": "deadline",
            "values": [job.get("application_deadline") for _, job, _ in jobs_data],
        }
    )

    return {
        "ok": True,
        "job_count": len(jobs),
        "has_fit": chosen is not None,
        "render": {
            "kind": "job_compare",
            "cv_id": chosen.cv_id if chosen is not None else None,
            "jobs": jobs,
            "rows": rows,
        },
    }


# --------------------------------------------------------------------------- #
# Tool 4: show_cv → cv_card                                                    #
# --------------------------------------------------------------------------- #


async def show_cv(session: AsyncSession, principal: Principal, args: dict) -> dict:
    err = _require_student(principal)
    if err:
        return err
    locale = _loc(args)
    lib = await _load_library(session, principal)
    chosen, short = _resolve_cv(
        principal,
        args.get("cv_id"),
        lib=lib,
        pending_tool="show_cv",
        pending_args=args,
        prompt_key="picker.chooseCvForShow",
        locale=locale,
    )
    if short is not None:
        return short
    assert chosen is not None

    if chosen.cv_input is not None:
        top_skills, experience, education, summary = _facets(chosen.cv_input)
    else:
        top_skills, experience, education, summary = [], 0, 0, None

    return {
        "ok": True,
        "cv_title": chosen.title,
        "skill_count": len(top_skills),
        "render": {
            "kind": "cv_card",
            "cv_id": chosen.cv_id,
            "title": chosen.title,
            "source": chosen.source,
            "updated_at": chosen.updated_at,
            "is_default": chosen.is_default,
            "summary": summary,
            "top_skills": top_skills,
            "experience_count": experience,
            "education_count": education,
            "view_path": f"/student/cv/{chosen.cv_id}",
        },
    }


# --------------------------------------------------------------------------- #
# Tool 5: compare_cvs → cv_compare                                            #
# --------------------------------------------------------------------------- #


def _strength_highlight(
    top_skills: list[dict], experience: int, education: int, locale: str
) -> str:
    if locale == "en":
        return f"{len(top_skills)} skills · {experience} experience · {education} education"
    return f"{len(top_skills)} kỹ năng · {experience} kinh nghiệm · {education} học vấn"


def _content_strength(cv_input: job_fit.CvInput) -> tuple[float, list[dict], int, int]:
    """Deterministic no-job "overall strength" of a CV (richness + freshness)."""
    top_skills, experience, education, _ = _facets(cv_input)
    levels = [s["level"] for s in top_skills if isinstance(s.get("level"), int)]
    avg_level = sum(levels) / len(levels) if levels else 50.0
    freshness = max(0.0, 1.0 - min(cv_input.last_updated_days, 365) / 365.0)
    strength = len(top_skills) * 2 + experience * 3 + education + avg_level / 20 + freshness * 2
    return strength, top_skills, experience, education


async def compare_cvs(session: AsyncSession, principal: Principal, args: dict) -> dict:
    err = _require_student(principal)
    if err:
        return err
    locale = _loc(args)
    lib = await _load_library(session, principal)
    usable = [c for c in lib if c.cv_input is not None]
    if not usable:
        return _no_cv_result(locale)

    raw_ids = args.get("cv_ids")
    if isinstance(raw_ids, list) and raw_ids:
        wanted = {str(u) for u in (_uuid_or_none(r) for r in raw_ids) if u is not None}
        selected = [c for c in usable if c.cv_id in wanted]
        if not selected:
            return {"ok": False, "error": "cv_not_found"}
    else:
        selected = usable

    job_id = _uuid_or_none(args.get("job_id"))
    job: dict | None = None
    if job_id is not None:
        from app.modules.opportunities.application import job_fit_read

        job = await job_fit_read.load_job_for_fit(
            session, job_id=job_id, persona=principal.persona or "student", locale=locale
        )

    entries: list[dict] = []
    recommended: str | None = None
    if job is not None:
        cv_inputs = [c.cv_input for c in selected if c.cv_input is not None]
        outcome = job_fit.evaluate(job, cv_inputs, stale_days=_stale_days())
        by_id = {f.cv_id: f for f in outcome.results}
        for c in selected:
            fit = by_id.get(c.cv_id)
            highlight = None
            if fit and fit.matched_skills:
                highlight = ", ".join([m for m in fit.matched_skills if m][:3]) or None
            entries.append(
                {
                    "cv_id": c.cv_id,
                    "title": c.title,
                    "fit_score": fit.score if fit else None,
                    "fit_band": _band_key(fit.score) if fit else None,
                    "highlight": highlight,
                    "view_path": f"/student/cv/{c.cv_id}",
                }
            )
        ranked = [e for e in entries if e["fit_score"] is not None]
        if ranked:
            recommended = max(ranked, key=lambda e: e["fit_score"])["cv_id"]
    else:
        strengths: list[tuple[_LibCv, float, list[dict], int, int]] = []
        for c in selected:
            assert c.cv_input is not None
            strength, top_skills, experience, education = _content_strength(c.cv_input)
            strengths.append((c, strength, top_skills, experience, education))
        strengths.sort(key=lambda x: -x[1])
        for c, _s, top_skills, experience, education in strengths:
            entries.append(
                {
                    "cv_id": c.cv_id,
                    "title": c.title,
                    "fit_score": None,
                    "fit_band": None,
                    "highlight": _strength_highlight(top_skills, experience, education, locale),
                    "view_path": f"/student/cv/{c.cv_id}",
                }
            )
        if strengths:
            recommended = strengths[0][0].cv_id

    return {
        "ok": True,
        "cv_count": len(entries),
        "recommended_cv_id": recommended,
        "render": {
            "kind": "cv_compare",
            "job_id": str(job_id) if job_id is not None else None,
            "job_title": job.get("title") if job is not None else None,
            "cvs": entries,
            "recommended_cv_id": recommended,
        },
    }
