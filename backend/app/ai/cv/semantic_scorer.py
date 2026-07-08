"""LLM semantic CV-JD fit EXPLAINER — on-demand HR-evaluator narrative layer.

Complements the deterministic ``job_fit.py`` score with a contextual narrative
that reasons about experience depth, certification equivalencies, and adjacent
skills the way an experienced HR evaluator would.

IMPORTANT — the LLM does NOT set the product score (owner decision 2026-07-06).
The deterministic 6-criteria ``job_fit.py`` score is authoritative and reproducible;
this module only produces the natural-language ``summary`` (and structured
matched/gap reasoning) shown as the "why". ``score`` on the result mirrors the
deterministic input purely so older callers keep a usable field — no caller
blends it into the number anymore. The call runs at ``temperature=0`` so the
same (CV, JD) yields the same explanation on every reload.

Architecture
------------
- Input: full JD projection dict, flattened CV evidence text (pre-extracted
  by the caller from CV sections, max 1200 chars), and the pre-computed
  deterministic score from ``job_fit.py`` (used only as context in the prompt).
- Output: ``SemanticFitResult`` dataclass whose ``score`` mirrors the
  deterministic input for backwards compatibility ONLY — the caller discards it
  and keeps the deterministic 6-criteria score as the product score. There is NO
  40/60 (or any) blend of deterministic + semantic; only ``summary`` is consumed.
  When the LLM is unavailable, ``ai_unavailable=True`` is set and the caller
  degrades to ``explanation: null``.
- Caching: the caller (the fit-score store) is responsible for persisting the
  explanation keyed on (job_id, cv_id, job_version, cv_version, prompt_version)
  so it is generated once per content version, not per request.
- Gateway: all LLM calls go through ``app.ai.cv.llm.generate_json_note``, which
  routes through the factory, output guard, and usage logger — no direct provider
  SDK calls.
- Prompt injection protection: raw CV bytes never enter the prompt. The caller
  passes ``cv_text`` and this module extracts only the credential/skills/
  experience sections (max 1200 chars total) before building the message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from app.ai.cv import grounding
from app.ai.cv.llm import generate_json_note
from app.ai.prompts.cv_fit_analysis.v3 import PROMPT_VERSION, SYSTEM_PROMPT, build_user_message
from app.shared.exceptions import AIUnavailableError

# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------

TASK_TYPE = "cv_fit_analysis"
_CV_EVIDENCE_MAX_CHARS = 1200


@dataclass
class MatchedEvidence:
    requirement: str
    cv_evidence: str | None
    strength: Literal["strong", "moderate", "weak"]
    reasoning: str


@dataclass
class MatchGap:
    requirement: str
    cv_evidence: str | None
    severity: Literal["hard", "soft"]
    reasoning: str
    suggestion: str


@dataclass
class SemanticFitResult:
    score: int
    summary: str
    matched_evidence: list[MatchedEvidence] = field(default_factory=list)
    gaps: list[MatchGap] = field(default_factory=list)
    overall_suggestion: str = ""
    is_ai_result: bool = True
    ai_unavailable: bool = False
    prompt_version: int = PROMPT_VERSION


def analysis_payload(result: SemanticFitResult) -> dict:
    """Leak-safe structured analysis for the API + persistence (JSON-round-trippable).

    This is the STRUCTURED matching detail that the caller used to discard — the
    per-requirement matched evidence (with an ``evidence_strength`` label), the
    confirmed gaps (each carrying its own advisory ``suggestion``), and the
    ``overall_suggestion``. It is returned by the on-demand fit-explanation
    sub-call and persisted per ``(cv_id, job_id)`` so a reload reuses it without
    re-invoking the model.

    The model-mirrored ``score`` is deliberately EXCLUDED — the deterministic
    6-criteria product score is authoritative and returned separately; exposing the
    model's number here would read as raw model confidence. No provider/model/
    token/prompt internals are ever present (the dataclass already carries none).
    """
    return {
        "overall_suggestion": result.overall_suggestion,
        "matched_evidence": [
            {
                "requirement": m.requirement,
                "cv_evidence": m.cv_evidence,
                "evidence_strength": m.strength,
                "reasoning": m.reasoning,
            }
            for m in result.matched_evidence
        ],
        "gaps": [
            {
                "requirement": g.requirement,
                "cv_evidence": g.cv_evidence,
                "severity": g.severity,
                "reasoning": g.reasoning,
                "suggestion": g.suggestion,
            }
            for g in result.gaps
        ],
    }


# ---------------------------------------------------------------------------
# CV evidence extraction (injection-resistant)
# ---------------------------------------------------------------------------

# Section heading patterns that mark relevant CV regions.
# Covers English terms + common Vietnamese CV section headers.
_EVIDENCE_SECTION_RE = re.compile(
    r"(?i)\b(skill|experience|education|certif|language|qualification|"
    r"project|achievement|award|publication|"
    r"kỹ năng|kinh nghiệm|học vấn|chứng chỉ|ngôn ngữ|"
    r"dự án|thành tích|chuyên môn|năng lực|công nghệ|trình độ)\b"
)

# Heuristic: first N lines of a typical CV are contact info / personal header
# (name, email, phone, address, LinkedIn). Skipping them when no structured
# section headers were found gets to the skills/experience content faster.
_CONTACT_HEADER_LINES = 20


def _extract_cv_evidence(cv_text: str) -> str:
    """Extract only the skills/experience/education/certifications text from a
    flat CV string and cap at ``_CV_EVIDENCE_MAX_CHARS``.

    When the CV text is short enough to fit entirely, it is returned as-is.
    Otherwise only lines that appear to be in a relevant section are kept.
    This prevents prompt injection from sections like "objective" or "hobbies"
    that might contain adversarial text.

    Fallback when no section headers are detected: skip the first
    ``_CONTACT_HEADER_LINES`` lines (typically name/email/phone/address) and
    take the next ``_CV_EVIDENCE_MAX_CHARS`` characters, which are more likely
    to contain skills and experience content.
    """
    if len(cv_text) <= _CV_EVIDENCE_MAX_CHARS:
        return cv_text.strip()

    lines = cv_text.splitlines()
    in_relevant = False
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if _EVIDENCE_SECTION_RE.search(stripped):
            in_relevant = True
        if in_relevant and stripped:
            kept.append(stripped)
        if len("\n".join(kept)) >= _CV_EVIDENCE_MAX_CHARS:
            break

    result = "\n".join(kept)
    if not result.strip():
        # No section headers found. CVs typically open with contact info
        # (name, email, phone, address) so skip the first N lines before
        # taking the evidence window.
        skip = min(_CONTACT_HEADER_LINES, max(0, len(lines) - 5))
        result = "\n".join(lines[skip:])
    if not result.strip():
        result = cv_text
    return result[:_CV_EVIDENCE_MAX_CHARS]


# ---------------------------------------------------------------------------
# JSON → dataclass parsing
# ---------------------------------------------------------------------------

def _parse_strength(raw: object) -> Literal["strong", "moderate", "weak"]:
    s = str(raw or "").lower()
    if s == "strong":
        return "strong"
    if s == "moderate":
        return "moderate"
    return "weak"


def _parse_severity(raw: object) -> Literal["hard", "soft"]:
    return "hard" if str(raw or "").lower() == "hard" else "soft"


def _parse_result(
    data: dict,
    deterministic_score: int,
    matched_skills: list[str],
) -> SemanticFitResult:
    """Parse the LLM JSON dict into ``SemanticFitResult``, clamping and
    sanitising each field so a malformed response never crashes the caller.

    POST-FILTER (ground-truth safety net): any LLM-reported gap whose
    ``requirement`` is semantically equivalent to a deterministically-matched
    skill is DROPPED. The deterministic engine already confirmed those skills are
    covered (including via synonyms/abbreviations), so they can never legitimately
    resurface as a gap. Equivalence is detected with the same ontology the
    deterministic matcher uses: the matched skills are expanded once
    (``grounding.normalize_expanded``) and each gap requirement is tested against
    that expanded corpus (``grounding.term_present``). This guarantees the
    explanation layer can never contradict the deterministic evidence — e.g.
    telling a candidate to "add Kubernetes" when their CV already writes "k8s" —
    even if the model disobeys the prompt.
    """
    matched_expanded = grounding.normalize_expanded(
        " . ".join(s for s in matched_skills if s and s.strip())
    )
    raw_score = data.get("score")
    try:
        score = max(0, min(100, int(raw_score)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        score = deterministic_score

    summary = str(data.get("summary") or "").strip()[:400]
    overall = str(data.get("overall_suggestion") or "").strip()[:400]

    matched: list[MatchedEvidence] = []
    for item in data.get("matched_evidence") or []:
        if not isinstance(item, dict):
            continue
        matched.append(
            MatchedEvidence(
                requirement=str(item.get("requirement") or "")[:200],
                cv_evidence=str(item["cv_evidence"])[:300] if item.get("cv_evidence") else None,
                strength=_parse_strength(item.get("strength")),
                reasoning=str(item.get("reasoning") or "")[:300],
            )
        )

    gaps: list[MatchGap] = []
    for item in data.get("gaps") or []:
        if not isinstance(item, dict):
            continue
        requirement = str(item.get("requirement") or "")[:200]
        # POST-FILTER: drop any gap equivalent to a deterministically-matched
        # skill. The matched skill is ground truth; a matched skill can never be
        # a gap, even if the model disobeyed the prompt.
        if (
            requirement.strip()
            and matched_expanded
            and grounding.term_present(requirement, matched_expanded)
        ):
            continue
        gaps.append(
            MatchGap(
                requirement=requirement,
                cv_evidence=str(item["cv_evidence"])[:300] if item.get("cv_evidence") else None,
                severity=_parse_severity(item.get("severity")),
                reasoning=str(item.get("reasoning") or "")[:300],
                suggestion=str(item.get("suggestion") or "")[:300],
            )
        )

    return SemanticFitResult(
        score=score,
        summary=summary,
        matched_evidence=matched,
        gaps=gaps,
        overall_suggestion=overall,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def analyze(
    *,
    job: dict,
    cv_text: str,
    cv_language: str,
    deterministic_score: int,
    matched_skills: list[str],
    gaps: list[str],
) -> SemanticFitResult:
    """Run the LLM semantic analysis and return a ``SemanticFitResult``.

    Produces the HR-evaluator narrative for the recommended CV. On any LLM
    failure, returns a graceful fallback result with ``ai_unavailable=True`` so
    the caller degrades to ``explanation: null`` — the deterministic score is
    unaffected either way.

    Runs at ``temperature=0`` so the explanation is reproducible for a given
    (CV, JD) content version. The caller persists it keyed on
    (job_id, cv_id, job_version, cv_version, ``PROMPT_VERSION``).
    """
    cv_evidence = _extract_cv_evidence(cv_text)
    output_language = cv_language if cv_language in ("vi", "en") else "en"

    user_message = build_user_message(
        job=job,
        cv_evidence=cv_evidence,
        deterministic_score=deterministic_score,
        matched_skills=matched_skills,
        deterministic_gaps=gaps,
        output_language=output_language,
    )

    try:
        data = await generate_json_note(
            task_type=TASK_TYPE,
            system_prompt=SYSTEM_PROMPT,
            user_content=user_message,
            temperature=0.0,
            max_tokens=2000,
        )
    except AIUnavailableError:
        return SemanticFitResult(
            score=deterministic_score,
            summary="",
            ai_unavailable=True,
        )

    result = _parse_result(data, deterministic_score, matched_skills)
    return result
