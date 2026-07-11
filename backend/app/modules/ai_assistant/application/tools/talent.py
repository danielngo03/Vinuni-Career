"""Partner talent-pool AI candidate-search tool (``search_candidates``).

Lets a recruiter find candidates by a free-text brief, an external JD, and/or
structured skill filters. The retrieval + AI rerank itself lives in the
talent-pool search SERVICE (owner decision 2026-07-10: embeddings + LLM rerank +
external-JD search — ``docs/PARTNER_RBAC_ANALYTICS_SPEC.md`` "Talent Pool — AI
Semantic Candidate Search Contract"). This tool is a thin, guarded ADAPTER over
that service — the service owns embeddings, LLM rerank, metering (UsageContext +
budget), audit, and the deterministic keyword/filter fallback.

Guardrails at this boundary (defense in depth on top of the service's own):

- RBAC: partner persona + the candidate-access capability (``candidate_identity:
  view_cv`` — the SAME grant the service enforces), re-checked HERE so the
  confirm/direct-dispatch path can never bypass RBAC just because the HTTP
  surface was protected.
- Input guard: free-text ``query_text`` / ``jd_text`` are sanitised
  (prompt-injection stripped, PII redacted) before they reach the ranker —
  untrusted instruction-in-data can never steer ranking.
- Output guard: match reasons are re-scrubbed of any provider/model/token
  leakage and contact PII; raw similarity scores / embedding internals are NEVER
  surfaced (the adapter builds an explicit allow-listed result dict — it forwards
  only a categorical ``match_tier`` and human-readable reasons, never a number).
- Graceful degradation: the service is resolved lazily through an INTEGRATION
  SEAM (:func:`_resolve_talent_search`). If it is not importable, the tool
  returns a user-safe "talent search unavailable" result instead of raising.

INTEGRATION SEAM (Lane A) — wired to
``app.modules.talent_pool.application.talent_search_service.search_talent``. If
Lane A renames/moves it, adjust ONLY :func:`_resolve_talent_search`; the guards +
result shaping below are stable.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.exceptions import (
    AIUnavailableError,
    AuthRequiredError,
    PaymentRequiredError,
    PermissionDeniedError,
    QuotaExceededError,
    ValidationFailedError,
)
from app.shared.permissions import Principal, permission_checker

# Cap on returned candidates (matches the talent-pool page-size ceiling).
_MAX_CANDIDATES = 20

# The candidate-access capability the talent service enforces (grep the RBAC
# catalog: ``candidate_identity: {view_cv, download_cv}``) — kept in sync so the
# tool-level gate and the service-level gate never disagree.
_RBAC_RESOURCE = "candidate_identity"
_RBAC_ACTION = "view_cv"


def _as_skill_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()][:30]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()][:30]
    return []


def _min_experience_from(filters: dict[str, Any]) -> int | None:
    """Pull a min-experience integer out of the loose ``filters`` object."""
    for key in ("min_experience", "experience_years", "min_experience_years", "years"):
        raw = filters.get(key)
        if raw is None or raw == "":
            continue
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            continue
    return None


def _resolve_talent_search():
    """Resolve Lane A's talent-pool AI search callable, or ``None`` if not wired.

    INTEGRATION SEAM. Lane A owns ``POST /talent-pool/search`` and its service.
    Primary target — ``talent_pool.application.talent_search_service.search_talent``::

        async def search_talent(
            session, *, principal, ctx, query_text, jd_text, skills,
            min_experience, limit, offset, locale,
        ) -> {"items": [{profile_id, display_name, match_tier, match_reasons,
                         matched_skills, ...}], "source": "ai_semantic"|"keyword_fallback",
              "page": {...}}

    Resolution order (first hit wins) — adjust ONLY here if Lane A renames things.
    """
    # (1) the real talent-pool service module
    try:
        from app.modules.talent_pool.application import talent_search_service

        fn = getattr(talent_search_service, "search_talent", None)
        if callable(fn):
            return fn
    except Exception:  # noqa: BLE001 - absence is expected pre-integration
        pass

    # (2) alternate seams (in case the service lands under student_profiles)
    try:
        from app.modules.student_profiles.application import (  # type: ignore[attr-defined]
            talent_search_service as tss,
        )

        fn = getattr(tss, "search_talent", None) or getattr(tss, "search_candidates", None)
        if callable(fn):
            return fn
    except Exception:  # noqa: BLE001
        pass

    return None


async def search_candidates(session: AsyncSession, principal: Principal, args: dict) -> dict:
    """Find candidates for a brief / external JD / skill filter (guarded adapter).

    Delegates ranking + metering + fallback to the talent-pool search service and
    returns an allow-listed, PII/leak-scrubbed structured result the model turns
    into a readable candidate list (never a raw similarity score).
    """
    from app.ai.gateway.output_guard import scrub_text
    from app.ai.safety.input_guard import redact_pii, sanitize_instruction
    from app.modules.auth.application.context import RequestContext

    if not principal.is_authenticated or principal.org_id is None:
        return {"ok": False, "error": "partner_auth_required"}

    # Defense-in-depth RBAC: the real-time/tool path re-checks the grant here,
    # independent of native_loop's authorize_tool pre-filter. The talent pool is a
    # cross-org VinUni candidate index, so this capability is NOT org-scoped
    # (matches the service's own ``permission_checker.require`` gate).
    if not permission_checker.can(principal, _RBAC_RESOURCE, _RBAC_ACTION):
        return {"ok": False, "error": "permission_denied"}

    # ---- input guard: sanitise free text BEFORE it reaches the ranker ----
    query_text, _q_flags = sanitize_instruction((args.get("query_text") or "")[:2000])
    jd_text, _jd_flags = sanitize_instruction((args.get("jd_text") or "")[:6000])
    skills = _as_skill_list(args.get("skills"))
    raw_filters = args.get("filters")
    filters: dict[str, Any] = raw_filters if isinstance(raw_filters, dict) else {}
    if not (query_text or jd_text or skills):
        return {"ok": False, "error": "empty_query"}

    limit = args.get("limit")
    try:
        limit_n = min(int(limit), _MAX_CANDIDATES) if limit else 10
    except (TypeError, ValueError):
        limit_n = 10
    locale = "en" if str(args.get("locale") or "vi").lower().startswith("en") else "vi"

    fn = _resolve_talent_search()
    if fn is None:
        # Graceful degradation — the service is not wired in this tree.
        return {
            "ok": False,
            "error": "talent_search_unavailable",
            "message": (
                "Talent search isn't available right now. You can browse candidates on "
                "the Talent Pool page (/partner/talent)."
            ),
        }

    try:
        raw = await fn(
            session,
            principal=principal,
            ctx=RequestContext(),
            query_text=query_text,
            jd_text=jd_text,
            skills=skills,
            min_experience=_min_experience_from(filters),
            limit=limit_n,
            locale=locale,
        )
    except ValidationFailedError:
        return {"ok": False, "error": "empty_query"}
    except (PermissionDeniedError, AuthRequiredError):
        return {"ok": False, "error": "permission_denied"}
    except (QuotaExceededError, PaymentRequiredError):
        return {
            "ok": False,
            "error": "quota_exceeded",
            "message": (
                "Your organisation has reached its AI usage limit for now. Deterministic "
                "browsing is still available on the Talent Pool page."
            ),
        }
    except AIUnavailableError:
        return {
            "ok": False,
            "error": "ai_unavailable",
            "message": (
                "AI ranking is temporarily unavailable. Try the Talent Pool page for a "
                "keyword + filter search."
            ),
        }
    except TypeError:
        # Integration drift: the resolved callable's signature changed. Fail safe.
        return {"ok": False, "error": "talent_search_unavailable"}
    except Exception:  # noqa: BLE001 - never surface a raw error to the model
        return {"ok": False, "error": "tool_failed"}

    if not isinstance(raw, dict):
        return {"ok": False, "error": "tool_failed"}
    if raw.get("ok") is False:
        return {"ok": False, "error": str(raw.get("error") or "tool_failed")}

    # The service returns ``items`` (identity summary + tier + reasons). Accept the
    # documented ``candidates`` alias too, in case a future seam uses it.
    rows = raw.get("items")
    if rows is None:
        rows = raw.get("candidates") or []

    candidates: list[dict] = []
    for c in rows[:_MAX_CANDIDATES]:
        if not isinstance(c, dict):
            continue
        # Output guard on every free-text reason: scrub provider/model/token
        # leakage, then redact any contact PII that slipped through.
        reasons = [
            redact_pii(scrub_text(str(r)))[0]
            for r in (c.get("match_reasons") or [])
            if str(r).strip()
        ][:4]
        gaps = [
            redact_pii(scrub_text(str(g)))[0]
            for g in (c.get("evidence_gaps") or [])
            if str(g).strip()
        ][:3]
        pid = c.get("profile_id")
        candidates.append(
            {
                # Allow-listed fields ONLY — no score/similarity/embedding/provider.
                "profile_id": str(pid) if pid else None,
                "display_name": c.get("display_name") or "Candidate",
                # Categorical fit tier (strong/good/possible) — never a number.
                "match_tier": c.get("match_tier"),
                "match_reasons": reasons,
                "evidence_gaps": gaps,
                "matched_skills": _as_skill_list(c.get("matched_skills"))[:8],
                "url": c.get("profile_url") or (f"/partner/talent/{pid}" if pid else None),
            }
        )

    source = str(raw.get("source") or "keyword_fallback")
    ai_ranked = bool(raw.get("ai_ranked", source == "ai_semantic"))
    return {
        "ok": True,
        "candidates": candidates,
        "total": len(candidates),
        "ai_ranked": ai_ranked,
        "source": source,
        "note": (
            "Ranked by fit to your brief/JD. Reasons are advisory — open each candidate's "
            "CV to verify. Similarity scores are never shown."
        ),
    }
