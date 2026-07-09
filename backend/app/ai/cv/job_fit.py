"""Deterministic CV-to-job fit scoring (``recommend_cv_for_job`` base layer).

The user-facing 0-100 ``score`` is a **product score**, computed from the full JD
projection (title, description, requirements, benefits, structured skills and
candidate criteria) and the CV's own content. It is not a model confidence,
embedding similarity, or hiring decision. The same inputs always produce the
same score, so it can be ranked, cached, tested, and explained without spending
a model call.

The score models how a real recruiter reads a CV against a JD, across SIX core
criteria (see ``BandScores``):

1. **Hard skills & tools** — coverage of the JD's required/preferred skills PLUS
   contextual depth (a skill proven inside a work-experience bullet counts for
   more than one merely listed in a "Skills" line).
2. **Work experience & relevance** — relevance of past work to the JD, total
   years vs the JD's minimum, and job-title / function / field alignment.
3. **Scope & impact** — leadership vs participation language, quantified impact
   (metrics, scale, budgets, team sizes), and seniority-level fit.
4. **Education & certifications** — degree level, language/GPA thresholds,
   professional certifications, and study-major alignment with the JD's field.
5. **Soft skills** — the soft skills the JD asks for, credited more when the CV
   proves them in context rather than listing them as bare keywords.
6. **Career trajectory** — job-hopping / tenure risk and how well the CV's
   career objective points at this role's path.

Partner-entered skill lists are useful but often incomplete or noisy, so scoring
combines explicit skills with inferred JD terms and role/field evidence.
Sensitive demographic requirements (gender, marital status, age, nationality)
are intentionally excluded so the score stays a job-fit signal, not a
protected-trait filter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache

from app.ai.cv import grounding
from app.ai.cv.proficiency_norm import (
    cefr_meets,
    gpa_meets,
    normalize_gpa_to_4,
    normalize_proficiency,
)

# --------------------------------------------------------------------------- #
# Scorer version + weights                                                    #
# --------------------------------------------------------------------------- #

# Scorer version stamp for the persisted CV-JD fit store. Bump this string
# whenever the band weights, matching logic, or ``term_expansion.py`` ontology
# change, so all persisted ``cv_job_fit_scores`` rows carrying an older stamp are
# treated as stale and lazily recomputed on the next read (see
# ``app.modules.documents.application.fit_store.is_fresh``).
#
# History (condensed): v2 VN ontology expansion; v3 added then v4 removed a
# semantic-embedding tier (the live model could not separate true VN↔EN skill
# pairs from confusables) — cross-lingual matching is now done by
# TRANSLATION-NORMALIZATION upstream (``app.ai.cv.skill_translation``), so this
# module is pure lexical; v5 word-boundary precision fix; v6 cross-lingual band
# coverage + dynamic "to present" dates; v7 grouped degree-level check; v8
# competency gate; v9 6 criteria incl. a standalone DOMAIN band.
#
# v10 (2026-07-07): rebuilt around the 6 REAL-HR criteria below. The standalone
# DOMAIN/industry band was REMOVED as redundant with skills (owner decision): a
# wrong-field candidate already has ~0 skill overlap and ~0 experience relevance.
# The industry taxonomy is retained but REUSED for (2) job-title/field relevance
# inside EXPERIENCE and (4) study-major alignment inside CREDENTIALS. New bands:
# SCOPE (leadership verbs + quantified impact + seniority fit — folds the old
# role/achievement/seniority signals), SOFT_SKILLS (JD soft skills proven in
# context), and TRAJECTORY (tenure/job-hopping + objective alignment). Skills now
# credits contextual depth. Gate core is SKILLS + EXPERIENCE (survival). Recompute
# all persisted rows.
SCORER_VERSION = "10"

# The 6 CORE HR evaluation criteria (weights must sum to 1.0). Skills is the
# survival signal ("sống còn") and carries the most weight; experience is the
# second pillar. Scope, credentials, soft skills, and trajectory refine the
# ranking between candidates who clear the skills+experience bar.
W_SKILLS = 0.30  # hard-skill coverage vs the JD + contextual depth
W_EXPERIENCE = 0.22  # relevance + years + job-title/field alignment
W_SCOPE = 0.15  # leadership vs participation + quantified impact + level fit
W_CREDENTIALS = 0.13  # degree/cert/language + study-major alignment
W_SOFT = 0.10  # JD-requested soft skills, credited for context proof
W_TRAJECTORY = 0.10  # tenure / job-hopping risk + career-objective alignment

# HR-realism competency gate (applied only when the JD specifies skills). The
# "core competency" — can they do THIS job at all — is skills + experience. When
# that core is weak, the whole score is scaled down so a candidate who lacks the
# required skills and has no relevant experience cannot be rescued by hygiene
# bands (soft skills, trajectory, credentials). At core=0 the score keeps
# ``_CORE_GATE_BASE`` of its value; at core>=floor there is no penalty.
_CORE_GATE_FLOOR = 55.0
_CORE_GATE_BASE = 0.30

# ``skills_en`` and ``translated_en`` are SYNTHETIC sections injected upstream by
# ``skill_translation.english_augment`` on the cross-lingual (VN→EN) path only.
# ``skills_en`` carries the English forms of the CV's skill items;
# ``translated_en`` carries the English translation of the CV's experience /
# education / summary / projects prose. Including them here lets the
# EXPERIENCE / CREDENTIALS bands see the English evidence when a Vietnamese CV is
# scored against an English JD. Offline they are never produced, so pure lexical
# scoring is unchanged.
_EXPERIENCE_TYPES = frozenset(
    {
        "experience",
        "work",
        "work_experience",
        "projects",
        "project",
        "internship",
        "skills_en",
        "translated_en",
    }
)
_ROLE_TYPES = frozenset(
    {
        "summary",
        "objective",
        "experience",
        "work",
        "work_experience",
        "projects",
        "project",
        "skills",
        "skills_en",
        "translated_en",
    }
)
_CREDENTIAL_TYPES = frozenset(
    {
        "education",
        "certifications",
        "certification",
        "licenses",
        "languages",
        "language",
        "translated_en",
    }
)
_OBJECTIVE_TYPES = frozenset({"summary", "objective", "translated_en"})
_EDUCATION_TYPES = frozenset({"education", "translated_en"})
_SKILL_SECTION_TYPES = frozenset({"skills", "skill", "skills_en"})

_JD_INFERRED_KEYWORDS = 20
_ROLE_KEYWORDS = 12

_NOISY_JD_TERMS = frozenset(
    {
        "about",
        "able",
        "benefit",
        "benefits",
        "business",
        "candidate",
        "candidates",
        "company",
        "description",
        "good",
        "great",
        "join",
        "must",
        "nice",
        "project",
        "projects",
        "requirement",
        "requirements",
        "responsibilities",
        "responsibility",
        "role",
        "team",
        "will",
        "work",
        "working",
        "ứng",
        "viên",
        "công",
        "việc",
        "doanh",
        "nghiệp",
        "mô",
        "tả",
        "yêu",
        "cầu",
        "quyền",
        "lợi",
        "đội",
        "nhóm",
        # Vietnamese noise syllables — standalone syllables appear in all JD prose
        # but carry no skill signal when isolated from their compound word.
        "kinh",
        "nghiệm",
        "phần",
        "mềm",
        "năm",
        "tháng",
        "nơi",
        "bằng",
        "được",
        "không",
        "hàng",
        "toàn",
        "thực",
        "thông",
        "trình",
        "dựng",
        "thống",
        "người",
        "tiếng",
        "giỏi",
        "hiểu",
    }
)

# Degree aliases (VN + EN). Bare "ba"/"ma" are deliberately excluded — as 2-char
# tokens they would word-boundary-match common Vietnamese words and falsely
# detect a degree. "bsc"/"msc" are unambiguous.
_DEGREE_TERMS = {
    "associate": ["associate", "cao đẳng"],
    "bachelor": ["bachelor", "bsc", "cử nhân", "đại học"],
    "master": ["master", "msc", "thạc sĩ"],
    "phd": ["phd", "doctorate", "tiến sĩ"],
}

# Degree ordering so a HIGHER degree satisfies a lower requirement (a master's
# meets a "bachelor required" JD). Used by the credentials band's level check.
_DEGREE_LEVEL = {"associate": 1, "bachelor": 2, "master": 3, "phd": 4}

_SENIORITY_TERMS = {
    "intern": ["intern", "internship", "thực tập", "thực tập sinh", "sinh viên thực tập"],
    "fresher": [
        "fresher",
        "entry level",
        "graduate",
        "mới tốt nghiệp",
        "tốt nghiệp mới",
        "fresh graduate",
    ],
    "junior": ["junior"],
    "middle": ["middle", "mid level", "mid-level", "trung cấp"],
    "senior": [
        "senior",
        "principal",
        "kỹ sư cao cấp",
        "nhân viên cấp cao",
        "chuyên gia",
        "cao cấp",
    ],
    "lead": [
        "lead",
        "principal",
        "staff",
        "trưởng nhóm",
        "trưởng phòng",
        "tech lead",
        "quản lý kỹ thuật",
    ],
}

_NO_EXPERIENCE_MODES = {"no_requirement", "fresher"}


# --------------------------------------------------------------------------- #
# Industry / field taxonomy                                                   #
# --------------------------------------------------------------------------- #
# A deterministic keyword classifier: the JD and the CV are each mapped to the
# industry whose signal terms appear most. It is NO LONGER a standalone band
# (that was redundant with skills). Instead the field distance is REUSED inside
# EXPERIENCE (job-title / function relevance) and CREDENTIALS (study-major
# alignment). This still lets a recruiter reject "Nursing CV for a DevSecOps
# role" while crediting "Full-Stack CV for a DevSecOps role" (same IT field),
# because those two bands feed the score and the competency gate.
_INDUSTRY_TERMS: dict[str, list[str]] = {
    "software_it": [
        "software",
        "developer",
        "programmer",
        "engineer",
        "backend",
        "frontend",
        "fullstack",
        "full-stack",
        "full stack",
        "devops",
        "devsecops",
        "sre",
        "web",
        "mobile",
        "api",
        "microservices",
        "cloud",
        "aws",
        "azure",
        "gcp",
        "kubernetes",
        "docker",
        "linux",
        "python",
        "java",
        "javascript",
        "typescript",
        "golang",
        "c++",
        "c#",
        "php",
        "ruby",
        "react",
        "node",
        "sql",
        "database",
        "cybersecurity",
        "security engineer",
        "infrastructure",
        "system administrator",
        "lập trình",
        "phần mềm",
        "kỹ sư phần mềm",
        "công nghệ thông tin",
        "cntt",
        "an ninh mạng",
        "an toàn thông tin",
        "hệ thống",
        "cơ sở dữ liệu",
    ],
    "data_ai": [
        "data scientist",
        "data engineer",
        "data analyst",
        "machine learning",
        "deep learning",
        "artificial intelligence",
        "nlp",
        "computer vision",
        "analytics",
        "big data",
        "tensorflow",
        "pytorch",
        "llm",
        "genai",
        "khoa học dữ liệu",
        "phân tích dữ liệu",
        "trí tuệ nhân tạo",
        "học máy",
    ],
    "design_ux": [
        "designer",
        "ux",
        "ui",
        "user experience",
        "user interface",
        "figma",
        "graphic design",
        "product design",
        "photoshop",
        "illustrator",
        "wireframe",
        "prototype",
        "thiết kế",
        "đồ họa",
        "trải nghiệm người dùng",
    ],
    "healthcare": [
        "nurse",
        "nursing",
        "doctor",
        "physician",
        "clinical",
        "patient",
        "hospital",
        "medical",
        "healthcare",
        "pharmacy",
        "pharmacist",
        "surgery",
        "therapy",
        "điều dưỡng",
        "y tá",
        "bác sĩ",
        "y khoa",
        "bệnh nhân",
        "bệnh viện",
        "y tế",
        "dược sĩ",
        "lâm sàng",
        "chăm sóc sức khỏe",
    ],
    "finance_accounting": [
        "finance",
        "financial",
        "accountant",
        "accounting",
        "banking",
        "audit",
        "auditor",
        "tax",
        "investment",
        "treasury",
        "actuary",
        "bookkeeping",
        "tài chính",
        "kế toán",
        "ngân hàng",
        "kiểm toán",
        "thuế",
        "đầu tư",
    ],
    "marketing_sales": [
        "marketing",
        "seo",
        "sem",
        "content",
        "brand",
        "advertising",
        "sales",
        "salesperson",
        "business development",
        "account manager",
        "social media",
        "copywriting",
        "public relations",
        "tiếp thị",
        "bán hàng",
        "kinh doanh",
        "quảng cáo",
        "thương hiệu",
        "truyền thông",
        "chăm sóc khách hàng",
    ],
    "hr_admin": [
        "human resources",
        "recruitment",
        "recruiter",
        "talent acquisition",
        "hr generalist",
        "payroll",
        "administrative",
        "office admin",
        "compensation",
        "nhân sự",
        "tuyển dụng",
        "hành chính",
        "tính lương",
    ],
    "education": [
        "teacher",
        "lecturer",
        "tutor",
        "professor",
        "curriculum",
        "education",
        "teaching",
        "instructor",
        "academic",
        "giáo viên",
        "giảng viên",
        "gia sư",
        "giáo dục",
        "sư phạm",
        "đào tạo",
        "giảng dạy",
    ],
    "manufacturing_engineering": [
        "manufacturing",
        "production",
        "mechanical",
        "electrical",
        "industrial",
        "maintenance",
        "assembly",
        "factory",
        "plant",
        "cnc",
        "automation engineer",
        "lean",
        "kaizen",
        "sản xuất",
        "cơ khí",
        "điện",
        "nhà máy",
        "vận hành máy",
        "may mặc",
        "dệt may",
        "kiểm soát chất lượng",
    ],
    "construction": [
        "construction",
        "civil engineer",
        "architect",
        "architecture",
        "site engineer",
        "surveyor",
        "building",
        "structural",
        "xây dựng",
        "kiến trúc",
        "công trình",
        "kỹ sư xây dựng",
        "giám sát công trường",
    ],
    "legal": [
        "lawyer",
        "legal",
        "attorney",
        "paralegal",
        "compliance",
        "contract law",
        "litigation",
        "luật",
        "luật sư",
        "pháp lý",
        "pháp chế",
        "hợp đồng",
    ],
    "hospitality_tourism": [
        "hotel",
        "restaurant",
        "tourism",
        "hospitality",
        "chef",
        "waiter",
        "barista",
        "receptionist",
        "travel",
        "khách sạn",
        "nhà hàng",
        "du lịch",
        "đầu bếp",
        "lễ tân",
        "phục vụ",
    ],
    "logistics_supplychain": [
        "logistics",
        "supply chain",
        "warehouse",
        "shipping",
        "freight",
        "procurement",
        "inventory",
        "fleet",
        "distribution",
        "chuỗi cung ứng",
        "kho vận",
        "kho bãi",
        "vận chuyển",
        "mua sắm",
        "đấu thầu",
    ],
}

# Adjacent-field groups: industries within one set share partial field credit.
_INDUSTRY_ADJACENCY: tuple[frozenset[str], ...] = (
    frozenset({"software_it", "data_ai", "design_ux"}),
    frozenset({"finance_accounting", "hr_admin", "legal"}),
    frozenset({"marketing_sales", "design_ux", "hr_admin"}),
    frozenset({"manufacturing_engineering", "construction", "logistics_supplychain"}),
)

_FIELD_SAME = 100  # same industry
_FIELD_ADJACENT = 55  # adjacent field (some transferable relevance)
_FIELD_UNRELATED = 15  # different world (Nursing vs Software)
_FIELD_UNKNOWN = 60  # can't classify one side — neutral, don't over-penalise
_INDUSTRY_MIN_HITS = 2  # need at least this many signal hits to claim an industry


@dataclass(slots=True)
class CvInput:
    """One active CV to score (already loaded + owner-checked by the service)."""

    cv_id: str
    title: str
    language: str
    sections: list[dict]
    last_updated_days: int


@dataclass(slots=True)
class BandScores:
    """The 6 core HR CV-JD fit criteria (each 0-100)."""

    skills: int
    experience: int
    scope: int
    credentials: int = 80  # default: JD states no credential requirement
    soft_skills: int = 70  # default: JD does not emphasise soft skills
    trajectory: int = 70  # default: not enough history to flag risk

    def as_dict(self) -> dict[str, int]:
        return {
            "skills": self.skills,
            "experience": self.experience,
            "scope": self.scope,
            "credentials": self.credentials,
            "soft_skills": self.soft_skills,
            "trajectory": self.trajectory,
        }


@dataclass(slots=True)
class CvFit:
    cv_id: str
    title: str
    score: int
    bands: BandScores
    matched_skills: list[str]
    gaps: list[str]
    stale: bool
    last_updated_days: int
    # Average self-rated proficiency (0-100) of the CV's leveled skills. Used ONLY
    # as a ranking tie-breaker between CVs with the SAME product score — it never
    # changes the score itself (owner decision 2026-07-06: self-ratings are noisy).
    # Neutral 50.0 when the CV states no numeric levels.
    avg_skill_level: float = 50.0


@dataclass(slots=True)
class JobFitOutcome:
    results: list[CvFit]
    recommended_cv_id: str | None
    signal: str
    requirement_count: int = 0


@dataclass(slots=True)
class _Requirements:
    required: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)
    inferred: list[str] = field(default_factory=list)
    role_terms: list[str] = field(default_factory=list)
    credential_terms: list[str] = field(default_factory=list)
    used_fallback: bool = False
    # Cross-lingual surfacing map: normalized-key(EN translation) -> original
    # display term. Populated ONLY on the augmented path (``english_augment``
    # writes ``job["_skill_translation_map"]``). Lets ``_skills_band`` collapse a
    # JD skill that carries BOTH its Vietnamese original AND its English
    # translation to a SINGLE user-facing entry. Empty on the pure-lexical path.
    translation_map: dict[str, str] = field(default_factory=dict)

    @property
    def all_terms(self) -> list[str]:
        return [
            *self.required,
            *self.preferred,
            *self.inferred,
            *self.role_terms,
            *self.credential_terms,
        ]

    @property
    def count(self) -> int:
        return (
            len(self.required)
            + len(self.preferred)
            + len(self.inferred)
            + len(self.role_terms)
            + len(self.credential_terms)
        )


def _clamp(score: int | float) -> int:
    return max(0, min(100, round(score)))


def _clean_terms(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        term = value.strip()
        key = grounding.normalize(term)
        if term and key and key not in seen and key not in _NOISY_JD_TERMS:
            seen.add(key)
            out.append(term)
    return out


def _dedupe_terms(values: list[str], *, limit: int | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        term = value.strip()
        key = grounding.normalize(term)
        if not term or not key or key in seen or key in _NOISY_JD_TERMS:
            continue
        seen.add(key)
        out.append(term)
        if limit is not None and len(out) >= limit:
            break
    return out


def _jd_text(job: dict) -> str:
    parts = [
        job.get("title"),
        job.get("description"),
        job.get("requirements"),
        job.get("benefits"),
        job.get("jd_text"),
    ]
    return " ".join(str(p) for p in parts if p)


def _keyword_terms(text: str, *, limit: int) -> list[str]:
    return _dedupe_terms(grounding.extract_keywords(text or "", limit=limit * 3), limit=limit)


def _degree_terms(value: object) -> list[str]:
    """The degree requirement as ONE grouped term (the canonical level name).

    Returning ``["bachelor"]`` (not each alias) means the credentials band
    evaluates the degree once via a level comparison instead of counting each
    alias — so a student holding "cử nhân" is not shown "bachelor" as a gap.
    """
    if not isinstance(value, str) or not value.strip():
        return []
    key = grounding.normalize(value)
    for canonical, aliases in _DEGREE_TERMS.items():
        if key == canonical or key in aliases or any(alias in key for alias in aliases):
            return [canonical]
    return [value.strip()]


def _detect_cv_degree_level(cv_text_norm: str) -> int:
    """Highest degree level evidenced anywhere in the CV text (0 = none found)."""
    best = 0
    for canonical, aliases in _DEGREE_TERMS.items():
        level = _DEGREE_LEVEL.get(canonical, 0)
        if level <= best:
            continue
        if any(grounding.term_present(v, cv_text_norm) for v in (canonical, *aliases)):
            best = level
    return best


def _seniority_terms(value: object) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return []
    key = grounding.normalize(value)
    terms = [value.strip()]
    for canonical, aliases in _SENIORITY_TERMS.items():
        if key == canonical or key in aliases or any(alias in key for alias in aliases):
            terms.extend(aliases)
            break
    return _dedupe_terms(terms, limit=5)


def _candidate_requirements(job: dict) -> dict:
    value = job.get("candidate_requirements")
    return value if isinstance(value, dict) else {}


def _group_values(group: object, *, include_note: bool = False) -> list[str]:
    if not isinstance(group, dict):
        return []
    mode = group.get("mode")
    if mode in (None, "not_required"):
        return []
    values = group.get("values")
    out = [v for v in values if isinstance(v, str)] if isinstance(values, list) else []
    if include_note and isinstance(group.get("note"), str):
        out.append(group["note"])
    return _dedupe_terms(out, limit=12)


def _credential_terms(job: dict) -> list[str]:
    reqs = _candidate_requirements(job)
    terms: list[str] = []
    terms.extend(_degree_terms(job.get("degree_required")))
    terms.extend(_group_values(reqs.get("education")))

    languages = reqs.get("languages")
    if isinstance(languages, list):
        for lang in languages:
            if not isinstance(lang, dict):
                continue
            name = lang.get("language")
            proficiency = lang.get("proficiency")
            if isinstance(name, str):
                terms.append(name)
            if isinstance(proficiency, str):
                terms.append(proficiency)

    certifications = reqs.get("certifications")
    if isinstance(certifications, list):
        for cert in certifications:
            if isinstance(cert, dict) and isinstance(cert.get("name"), str):
                terms.append(cert["name"])

    return _dedupe_terms(terms, limit=18)


def _role_terms(job: dict) -> list[str]:
    terms: list[str] = []
    title = str(job.get("title") or "")
    terms.extend(_keyword_terms(title, limit=8))
    terms.extend(_seniority_terms(job.get("seniority_level")))
    # Add a few JD body terms so titles like "Associate" still get field signal.
    terms.extend(_keyword_terms(_jd_text(job), limit=_ROLE_KEYWORDS))
    return _dedupe_terms(terms, limit=_ROLE_KEYWORDS)


def _inferred_terms(job: dict, explicit: list[str]) -> list[str]:
    seen = {grounding.normalize(t) for t in explicit}
    terms: list[str] = []
    for term in _keyword_terms(_jd_text(job), limit=_JD_INFERRED_KEYWORDS):
        key = grounding.normalize(term)
        if key not in seen:
            terms.append(term)
    return _dedupe_terms(terms, limit=_JD_INFERRED_KEYWORDS)


def resolve_requirements(job: dict) -> _Requirements:
    """Resolve all terms used for scoring.

    Structured JD skills are kept as explicit requirements. Terms inferred from
    free-form JD copy supplement them but do not replace the source of truth.
    """

    required = _clean_terms(job.get("required_skills"))
    preferred = _clean_terms(job.get("preferred_skills"))
    explicit = [*required, *preferred]
    role_terms = _role_terms(job)
    credential_terms = _credential_terms(job)
    inferred = _inferred_terms(job, [*explicit, *role_terms, *credential_terms])
    raw_map = job.get("_skill_translation_map")
    translation_map = (
        {str(k): str(v) for k, v in raw_map.items()} if isinstance(raw_map, dict) else {}
    )
    return _Requirements(
        required=required,
        preferred=preferred,
        inferred=inferred,
        role_terms=role_terms,
        credential_terms=credential_terms,
        used_fallback=not bool(explicit),
        translation_map=translation_map,
    )


def _split_present(terms: list[str], text_norm_expanded: str) -> tuple[list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    for term in terms:
        if grounding.term_present(term, text_norm_expanded):
            present.append(term)
        else:
            missing.append(term)
    return present, missing


def _section_type(section: dict) -> str:
    return grounding.normalize(str(section.get("section_type") or "")).replace(" ", "_")


def _section_text(sections: list[dict], types: frozenset[str]) -> str:
    parts = [
        grounding.content_to_text(s.get("content")) for s in sections if _section_type(s) in types
    ]
    return " ".join(p for p in parts if p)


def _collapse_translations(
    values: list[str], translation_map: dict[str, str], *, limit: int
) -> list[str]:
    """Dedupe surfaced skill terms, collapsing VN original + its EN translation.

    ``translation_map`` maps ``normalize(variant) -> canonical display`` for BOTH
    a Vietnamese original AND its appended English translation. So a JD carrying
    "quản lý chuỗi cung ứng" AND "supply chain management" surfaces ONE entry.
    Terms absent from the map collapse to themselves — a no-op offline.
    """
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        term = value.strip()
        key = grounding.normalize(term)
        if not term or not key or key in _NOISY_JD_TERMS:
            continue
        display = translation_map.get(key, term)
        dedup_key = grounding.normalize(display)
        if not dedup_key or dedup_key in seen:
            continue
        seen.add(dedup_key)
        out.append(display)
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- #
# Field / industry helpers (reused by EXPERIENCE + CREDENTIALS)               #
# --------------------------------------------------------------------------- #


@lru_cache(maxsize=2048)
def _classify_industry_norm(text_norm: str) -> str | None:
    """Classify an ALREADY normalize-expanded text (no re-expansion).

    ``normalize_expanded`` (synonym expansion over the whole text) is the hot cost
    when scoring large CVs across many jobs, so callers that already hold the
    expanded CV text (``score_cv``'s ``cv_text_norm``) must reuse it via this
    variant instead of re-expanding through ``_classify_industry``.
    """
    best: str | None = None
    best_hits = 0
    for industry, terms in _INDUSTRY_TERMS.items():
        hits = sum(1 for term in terms if grounding.term_present(term, text_norm))
        if hits > best_hits:
            best_hits = hits
            best = industry
    return best if best_hits >= _INDUSTRY_MIN_HITS else None


def _classify_industry(text: str) -> str | None:
    """The industry whose signal terms appear most in ``text`` (None if < min)."""
    return _classify_industry_norm(grounding.normalize_expanded(text))


def _industries_adjacent(a: str, b: str) -> bool:
    return any(a in group and b in group for group in _INDUSTRY_ADJACENCY)


def _field_closeness(jd_ind: str | None, cv_ind: str | None) -> int:
    """0-100 closeness of two classified fields (neutral when either unknown)."""
    if jd_ind is None or cv_ind is None:
        return _FIELD_UNKNOWN
    if jd_ind == cv_ind:
        return _FIELD_SAME
    if _industries_adjacent(jd_ind, cv_ind):
        return _FIELD_ADJACENT
    return _FIELD_UNRELATED


def _jd_industry(job: dict, req: _Requirements) -> str | None:
    """Classify the JD's industry — partner-set field first, else from JD text."""
    parts = [str(job.get("title") or ""), " ".join(req.all_terms), _jd_text(job)]
    explicit = job.get("industry") or job.get("industry_name")
    if isinstance(explicit, str) and explicit.strip():
        parts.insert(0, explicit)
    return _classify_industry(" ".join(p for p in parts if p))


# --------------------------------------------------------------------------- #
# Band 1: Hard skills & tools (coverage + contextual depth)                   #
# --------------------------------------------------------------------------- #


def _skills_band(
    req: _Requirements,
    cv_text_norm: str,
    experience_norm: str,
) -> tuple[int, list[str], list[str]]:
    pres_req, miss_req = _split_present(req.required, cv_text_norm)
    pres_pref, miss_pref = _split_present(req.preferred, cv_text_norm)
    pres_inf, miss_inf = _split_present(req.inferred, cv_text_norm)

    explicit_score: int | None = None
    if req.required or req.preferred:
        req_cov = (len(pres_req) / len(req.required)) if req.required else None
        pref_cov = (len(pres_pref) / len(req.preferred)) if req.preferred else None
        if req_cov is not None and pref_cov is not None:
            explicit_score = _clamp(100 * (0.8 * req_cov + 0.2 * pref_cov))
        elif req_cov is not None:
            explicit_score = _clamp(100 * req_cov)
        elif pref_cov is not None:
            explicit_score = _clamp(100 * pref_cov)

    inferred_score = _clamp(100 * len(pres_inf) / len(req.inferred)) if req.inferred else None
    if explicit_score is not None and inferred_score is not None:
        coverage_score = _clamp(0.75 * explicit_score + 0.25 * inferred_score)
    elif explicit_score is not None:
        coverage_score = explicit_score
    elif inferred_score is not None:
        coverage_score = inferred_score
    else:
        coverage_score = 55

    # --- Contextual depth ---------------------------------------------------
    # A matched skill proven inside a work-experience/project bullet is stronger
    # evidence than one only listed in a "Skills" line. We compute the fraction of
    # matched JD skills that also appear in the experience sections and use it as a
    # gentle multiplier (0.85..1.0) — a purely-listed skill set loses up to 15 %,
    # a fully-demonstrated one keeps the full coverage score. It only ADJUSTS
    # coverage (never invents credit), so it can't lift a low-coverage CV.
    matched_terms = [*pres_req, *pres_pref]
    if matched_terms and experience_norm:
        in_context = sum(1 for t in matched_terms if grounding.term_present(t, experience_norm))
        depth_ratio = in_context / len(matched_terms)
    else:
        depth_ratio = 0.0
    score = _clamp(coverage_score * (0.85 + 0.15 * depth_ratio))

    # Only the partner-curated skill strings are surfaced as user-facing evidence.
    # Terms inferred from free-form JD prose feed the score but are never echoed
    # (would leak raw JD copy / prompt-injection text). Cross-lingual collapse folds
    # a VN original + its EN translation to one display term.
    tmap = req.translation_map
    matched = _collapse_translations([*pres_req, *pres_pref], tmap, limit=14)
    matched_keys = {grounding.normalize(m) for m in matched}
    gaps = [
        g
        for g in _collapse_translations([*miss_req, *miss_pref], tmap, limit=14)
        if grounding.normalize(g) not in matched_keys
    ]
    return score, matched, gaps


# --------------------------------------------------------------------------- #
# Band 2: Work experience & relevance (relevance + years + title/field)       #
# --------------------------------------------------------------------------- #


def _minimum_experience(job: dict) -> float | None:
    mode = (job.get("experience_mode") or "").lower()
    if mode in _NO_EXPERIENCE_MODES:
        return None
    value = job.get("experience_min_years")
    if isinstance(value, int | float):
        return float(value)
    return None


_DATE_RANGE_RE = re.compile(
    r"(?:tháng\s+)?(\d{1,2})[/.](\d{4})"
    r"\s*(?:-|–|đến|to)\s*"
    r"(?:(?:tháng\s+)?(\d{1,2})[/.](\d{4})|nay|hiện\s*tại|present|now)",
    re.IGNORECASE,
)


def _job_durations(text: str) -> list[float]:
    """Every date-range tenure (in years) found in ``text``.

    Open-ended ("to present"/"đến nay") ranges anchor to the current date so they
    don't understate as time passes. Used by TRAJECTORY (job-hopping) and by
    ``_estimate_years`` (total experience).
    """
    now = datetime.now(tz=UTC)
    out: list[float] = []
    for m in _DATE_RANGE_RE.finditer(text):
        start_m, start_y = int(m.group(1)), int(m.group(2))
        if m.group(3) and m.group(4):
            end_m, end_y = int(m.group(3)), int(m.group(4))
        else:
            end_m, end_y = now.month, now.year
        duration = (end_y - start_y) + (end_m - start_m) / 12.0
        if duration > 0:
            out.append(duration)
    return out


def _estimate_years(text: str) -> float | None:
    """Best estimate of total years of experience evidenced in ``text``."""
    years: list[float] = [
        float(m.group(1).replace(",", "."))
        for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:years?|yrs?|năm)", text)
    ]
    # Month-count: "6 tháng kinh nghiệm" → 0.5 years
    years.extend(float(m.group(1)) / 12.0 for m in re.finditer(r"(\d+)\s*tháng", text))
    years.extend(_job_durations(text))
    return max(years) if years else None


def _role_terms_coverage(req: _Requirements, role_evidence: str) -> int:
    """Job-title / function keyword coverage in the CV's role-bearing sections."""
    if not req.role_terms:
        return 70
    present, _ = _split_present(req.role_terms, role_evidence)
    coverage = len(present) / len(req.role_terms)
    if coverage == 0:
        return 35
    return _clamp(35 + 65 * coverage)


def _experience_band(
    req: _Requirements,
    job: dict,
    sections: list[dict],
    cv_text_norm: str,
    field_score: int,
) -> int:
    """Relevance of past work + years vs required + job-title/field alignment."""
    evidence = grounding.normalize_expanded(_section_text(sections, _EXPERIENCE_TYPES))
    role_evidence = (
        grounding.normalize_expanded(_section_text(sections, _ROLE_TYPES)) or cv_text_norm
    )
    min_years = _minimum_experience(job)
    mode = (job.get("experience_mode") or "").lower()

    # Job-title / function relevance: role-keyword coverage blended with the CV↔JD
    # field distance (reuses the industry taxonomy). This is what makes a same-field
    # CV outrank a wrong-field one even before the competency gate.
    title_score = _clamp(0.55 * _role_terms_coverage(req, role_evidence) + 0.45 * field_score)

    if not evidence:
        # No experience section: lean on title/field signal but stay cautious when
        # the JD demands years the CV can't evidence.
        if min_years is None or mode in _NO_EXPERIENCE_MODES:
            return _clamp(0.5 * 55 + 0.5 * title_score)
        return _clamp(0.65 * 25 + 0.35 * title_score)

    terms = _dedupe_terms([*req.required, *req.preferred, *req.inferred, *req.role_terms], limit=24)
    if terms:
        present, _ = _split_present(terms, evidence)
        relevance = len(present) / len(terms)
    else:
        relevance = 0.7
    relevance_score = _clamp(40 + 60 * relevance)

    if min_years is None or min_years <= 0:
        return _clamp(0.6 * relevance_score + 0.4 * title_score)

    estimated = _estimate_years(evidence) or _estimate_years(cv_text_norm)
    if estimated is None:
        years_score = 55 if min_years <= 1 else 35
    else:
        years_score = _clamp(100 * min(estimated / min_years, 1.0))
    return _clamp(0.45 * relevance_score + 0.30 * title_score + 0.25 * years_score)


# --------------------------------------------------------------------------- #
# Band 3: Scope & impact (leadership + metrics + seniority fit)               #
# --------------------------------------------------------------------------- #

_IMPACT_RE = re.compile(
    r"(?:"
    r"\d+\s*%"
    r"|(?:increased?|decreased?|reduced?|improved?|grew?|scaled?|boosted?)"
    r"\s+\w+(?:\s+\w+)?\s+by\s+\d+"
    r"|\d+(?:[,.]?\d+)?\s*[km]\+?\s*"
    r"(?:users?|người\s*dùng|requests?|transactions?|customers?|orders?)"
    r"|(?:led|managed|supervised|mentored|quản\s*lý|dẫn\s*dắt|lãnh\s*đạo)"
    r"\s+(?:a?\s*team\s+of\s+)?(?:\w+\s+)?\d+"
    r"|hàng\s+(?:triệu|ngàn|nghìn|chục|trăm)\s+\w+"
    r"|(?:ngân\s*sách|budget|doanh\s*thu|revenue)\s+[^.\n]{0,20}\d"
    r"|(?:top|rank|hạng)\s*[#]?\d+"
    r")",
    re.IGNORECASE,
)
_ACHIEVEMENT_TYPES = _EXPERIENCE_TYPES | frozenset({"projects", "project", "activities"})

# Leadership vs participation language. Leadership verbs signal ownership/scope;
# participation verbs signal a supporting contribution. A Senior/Lead JD expects
# leadership evidence. Matched with boundary-aware normalized containment.
_LEAD_VERBS = frozenset(
    {
        "led",
        "lead",
        "leading",
        "manage",
        "managed",
        "managing",
        "direct",
        "directed",
        "architect",
        "architected",
        "own",
        "owned",
        "drove",
        "drive",
        "spearhead",
        "spearheaded",
        "oversee",
        "oversaw",
        "supervise",
        "supervised",
        "mentor",
        "mentored",
        "founded",
        "established",
        "launched",
        "built",
        "headed",
        "coordinated",
        "quản lý",
        "dẫn dắt",
        "lãnh đạo",
        "phụ trách",
        "chịu trách nhiệm",
        "điều hành",
        "chủ trì",
        "xây dựng",
        "triển khai",
        "thiết kế",
        "giám sát",
        "đứng đầu",
    }
)
_PARTICIPATE_VERBS = frozenset(
    {
        "participated",
        "participate",
        "assisted",
        "assist",
        "supported",
        "support",
        "helped",
        "help",
        "contributed",
        "contribute",
        "involved",
        "tham gia",
        "hỗ trợ",
        "phụ giúp",
        "góp phần",
        "cộng tác",
    }
)


@lru_cache(maxsize=2048)
def _count_verb_hits(text_norm: str, verbs: frozenset[str]) -> int:
    return sum(1 for v in verbs if grounding.term_present(v, text_norm))


def _impact_score(exp_text: str) -> int:
    """Quantified-impact signal from experience/project sections."""
    if not exp_text:
        return 45  # no experience section — can't assess
    hits = len(_IMPACT_RE.findall(exp_text))
    if hits == 0:
        return 45
    if hits == 1:
        return 65
    if hits <= 3:
        return 82
    return 97


def _leadership_score(exp_norm: str, jd_wants_senior: bool) -> int:
    lead = _count_verb_hits(exp_norm, _LEAD_VERBS)
    participate = _count_verb_hits(exp_norm, _PARTICIPATE_VERBS)
    if lead == 0 and participate == 0:
        base = 55  # no scope language either way — neutral
    else:
        ratio = lead / (lead + participate)
        base = _clamp(45 + 55 * ratio)
    # A senior/lead JD needs demonstrated ownership; pure participation caps low.
    if jd_wants_senior and lead == 0:
        base = min(base, 40)
    return base


def _scope_band(
    job: dict,
    req: _Requirements,
    sections: list[dict],
    cv_text_norm: str,
) -> int:
    exp_text = _section_text(sections, _ACHIEVEMENT_TYPES)
    exp_norm = grounding.normalize_expanded(exp_text) or cv_text_norm
    jd_level = _detect_seniority(
        grounding.normalize(job.get("title") or "")
        + " "
        + " ".join(grounding.normalize(t) for t in req.role_terms)
    )
    jd_wants_senior = jd_level in ("senior", "lead")

    impact = _impact_score(exp_text)
    leadership = _leadership_score(exp_norm, jd_wants_senior)
    seniority = _seniority_band(job, req, cv_text_norm)
    return _clamp(0.40 * impact + 0.35 * leadership + 0.25 * seniority)


# --- Seniority level alignment (feeds SCOPE) -------------------------------- #

_LEVEL_ORDER = ("intern", "fresher", "junior", "middle", "senior", "lead")
_LEVEL_NUM: dict[str, int] = {lvl: i for i, lvl in enumerate(_LEVEL_ORDER)}
_SEN_BOUNDARY_CACHE: dict[str, re.Pattern[str]] = {}


def _seniority_term_in(term: str, text: str) -> bool:
    """Boundary-aware containment for a normalised seniority term in *text*."""
    if " " in term or len(term) >= 7:
        return term in text
    pattern = _SEN_BOUNDARY_CACHE.get(term)
    if pattern is None:
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])")
        _SEN_BOUNDARY_CACHE[term] = pattern
    return bool(pattern.search(text))


@lru_cache(maxsize=2048)
def _detect_seniority(text: str) -> str | None:
    """Return the highest seniority level term found in ``text``."""
    highest = -1
    found: str | None = None
    for level in _LEVEL_ORDER:
        for term in _SENIORITY_TERMS[level]:
            if _seniority_term_in(grounding.normalize(term), text):
                lvl_num = _LEVEL_NUM[level]
                if lvl_num > highest:
                    highest = lvl_num
                    found = level
    return found


def _seniority_band(job: dict, req: _Requirements, cv_text_norm: str) -> int:
    """Seniority alignment: does the candidate's level match the role's level?"""
    jd_text = (
        grounding.normalize(job.get("title") or "")
        + " "
        + " ".join(grounding.normalize(t) for t in req.role_terms)
    )
    jd_level = _detect_seniority(jd_text)
    cv_level = _detect_seniority(cv_text_norm)

    if jd_level is None:
        return 70  # JD doesn't specify seniority → neutral
    if cv_level is None:
        return 55  # CV gives no seniority signal → slight uncertainty

    diff = _LEVEL_NUM[cv_level] - _LEVEL_NUM[jd_level]
    if diff == 0:
        return 100
    if diff == 1:
        return 80
    if diff == -1:
        return 55
    if diff >= 2:
        return 70  # clearly overqualified — may decline offer
    return 25  # diff <= -2: clearly too junior — hard gap


# --------------------------------------------------------------------------- #
# Band 4: Education & certifications (requirements + study-major alignment)   #
# --------------------------------------------------------------------------- #

_PROFICIENCY_SIGNALS = frozenset(
    {
        "ielts",
        "toefl",
        "toeic",
        "aptis",
        "pte",
        "duolingo",
        "vstep",
        "cefr",
        "english",
        "tiếng anh",
        "french",
        "tiếng pháp",
        "japanese",
        "tiếng nhật",
        "chinese",
        "tiếng trung",
        " b1",
        " b2",
        " c1",
        " c2",
        " a1",
        " a2",
    }
)
_GPA_SIGNALS = frozenset({"gpa", "grade point", "điểm trung bình"})


def _looks_like_proficiency(term: str) -> bool:
    t = term.lower()
    return any(sig in t for sig in _PROFICIENCY_SIGNALS)


def _looks_like_gpa(term: str) -> bool:
    t = term.lower()
    return any(sig in t for sig in _GPA_SIGNALS)


def _cv_credential_text(sections: list[dict], cv_text_norm: str) -> str:
    raw = _section_text(sections, _CREDENTIAL_TYPES)
    return raw if raw.strip() else cv_text_norm


def _credential_coverage(
    req: _Requirements,
    sections: list[dict],
    cv_text_norm: str,
) -> tuple[int | None, list[str], list[str]]:
    """Coverage of the JD's explicit credential requirements (None if none)."""
    if not req.credential_terms:
        return None, [], []

    evidence_expanded = (
        grounding.normalize_expanded(_section_text(sections, _CREDENTIAL_TYPES)) or cv_text_norm
    )
    cv_raw = _cv_credential_text(sections, cv_text_norm)

    present: list[str] = []
    missing: list[str] = []

    for term in req.credential_terms:
        norm_term = grounding.normalize(term)
        # --- Degree level comparison (one grouped requirement) ---
        if norm_term in _DEGREE_LEVEL:
            cv_level = _detect_cv_degree_level(evidence_expanded or cv_raw)
            (present if cv_level >= _DEGREE_LEVEL[norm_term] else missing).append(term)
            continue

        # --- CEFR language proficiency comparison ---
        if _looks_like_proficiency(term):
            required_cefr = normalize_proficiency(term)
            if required_cefr is not None:
                cv_cefr = normalize_proficiency(cv_raw)
                if cv_cefr is not None:
                    (present if cefr_meets(cv_cefr, required_cefr) else missing).append(term)
                    continue

        # --- GPA comparison ---
        if _looks_like_gpa(term):
            required_gpa = normalize_gpa_to_4(term)
            if required_gpa is not None:
                result = gpa_meets(cv_raw, required_gpa)
                if result is True:
                    present.append(term)
                elif result is False:
                    missing.append(term)
                else:
                    hit = grounding.term_present(term, evidence_expanded)
                    (present if hit else missing).append(term)
                continue

        # --- Default: expansion-aware substring matching ---
        (present if grounding.term_present(term, evidence_expanded) else missing).append(term)

    coverage = len(present) / len(req.credential_terms)
    return _clamp(45 + 55 * coverage), present, missing


def _credentials_band(
    req: _Requirements,
    sections: list[dict],
    cv_text_norm: str,
    jd_ind: str | None,
) -> tuple[int, list[str], list[str]]:
    """Requirement coverage blended with study-major alignment to the JD field."""
    coverage_score, present, missing = _credential_coverage(req, sections, cv_text_norm)

    # Study-major alignment: only meaningful when we can classify the JD's field.
    # When the JD field is unknown, major fit is unknowable, so we do NOT dilute a
    # satisfied credential requirement. When it is known, we classify the CV's
    # education section (falling back to the whole CV) and blend the field distance
    # in — a finance JD credits a finance/accounting major over an unrelated one.
    major_score: int | None = None
    if jd_ind is not None:
        edu_ind = _classify_industry(_section_text(sections, _EDUCATION_TYPES))
        # cv_text_norm is already normalize-expanded — reuse it (no re-expansion).
        major_score = _field_closeness(jd_ind, edu_ind or _classify_industry_norm(cv_text_norm))

    if coverage_score is None:
        # JD states no explicit credential requirement: neutral baseline, nudged by
        # major alignment when the JD field is known.
        if major_score is None:
            return 80, present, missing
        return _clamp(0.6 * 78 + 0.4 * major_score), present, missing
    if major_score is None:
        return coverage_score, present, missing
    return _clamp(0.75 * coverage_score + 0.25 * major_score), present, missing


# --------------------------------------------------------------------------- #
# Band 5: Soft skills (JD-requested, credited for context proof)              #
# --------------------------------------------------------------------------- #

_SOFT_SKILLS: dict[str, list[str]] = {
    "communication": ["communication", "communicate", "giao tiếp", "truyền đạt"],
    "teamwork": [
        "teamwork",
        "team work",
        "collaboration",
        "làm việc nhóm",
        "làm việc theo nhóm",
        "phối hợp",
    ],
    "leadership": ["leadership", "lãnh đạo", "dẫn dắt"],
    "problem_solving": ["problem solving", "problem-solving", "giải quyết vấn đề"],
    "critical_thinking": [
        "critical thinking",
        "analytical thinking",
        "tư duy phản biện",
        "tư duy phân tích",
    ],
    "time_management": ["time management", "quản lý thời gian"],
    "adaptability": ["adaptability", "adaptable", "flexible", "thích nghi", "linh hoạt"],
    "presentation": ["presentation", "present", "thuyết trình"],
    "negotiation": ["negotiation", "negotiate", "đàm phán", "thương lượng"],
    "creativity": ["creativity", "creative", "sáng tạo"],
    "attention_to_detail": [
        "attention to detail",
        "detail-oriented",
        "cẩn thận",
        "tỉ mỉ",
        "chi tiết",
    ],
    "work_under_pressure": ["under pressure", "chịu áp lực", "chịu được áp lực"],
    "proactivity": ["proactive", "self-motivated", "chủ động", "tự giác"],
}


def _soft_skills_band(job: dict, sections: list[dict], cv_text_norm: str) -> int:
    """Match the soft skills the JD asks for, crediting in-context proof."""
    jd_norm = grounding.normalize_expanded(_jd_text(job))
    jd_soft = [
        canon
        for canon, aliases in _SOFT_SKILLS.items()
        if any(grounding.term_present(a, jd_norm) for a in aliases)
    ]
    if not jd_soft:
        return 70  # JD does not emphasise soft skills → neutral, don't penalise

    exp_norm = grounding.normalize_expanded(_section_text(sections, _EXPERIENCE_TYPES))
    present = 0
    in_context = 0
    for canon in jd_soft:
        aliases = _SOFT_SKILLS[canon]
        if any(grounding.term_present(a, cv_text_norm) for a in aliases):
            present += 1
            if exp_norm and any(grounding.term_present(a, exp_norm) for a in aliases):
                in_context += 1
    if present == 0:
        return 30
    coverage = present / len(jd_soft)
    context_ratio = in_context / present
    return _clamp(coverage * 100 * (0.85 + 0.15 * context_ratio))


# --------------------------------------------------------------------------- #
# Band 6: Career trajectory (tenure / job-hopping + objective alignment)      #
# --------------------------------------------------------------------------- #


def _tenure_score(sections: list[dict]) -> int:
    """Job-hopping risk from per-role tenures. Neutral when history is thin."""
    durations = _job_durations(_section_text(sections, _EXPERIENCE_TYPES))
    if len(durations) >= 2:
        short = sum(1 for d in durations if d < 0.5)  # < 6 months
        avg = sum(durations) / len(durations)
        if short >= 2:
            return 40  # repeated job-hopping — a real HR risk flag
        if short == 1:
            return 62
        if avg >= 2.0:
            return 95
        if avg >= 1.0:
            return 82
        return 70
    if len(durations) == 1:
        return 78 if durations[0] >= 1.0 else 66
    return 70  # student / no dated history — neutral, never penalise


def _objective_alignment(req: _Requirements, sections: list[dict]) -> int:
    """Does the CV's career objective point at this role's path/field?"""
    obj_text = _section_text(sections, _OBJECTIVE_TYPES)
    if not obj_text.strip():
        return 65  # no stated objective — mild neutral
    obj_norm = grounding.normalize_expanded(obj_text)
    targets = _dedupe_terms([*req.role_terms, *req.required, *req.inferred], limit=16)
    if not targets:
        return 70
    present, _ = _split_present(targets, obj_norm)
    return _clamp(45 + 55 * (len(present) / len(targets)))


def _trajectory_band(req: _Requirements, sections: list[dict]) -> int:
    return _clamp(0.6 * _tenure_score(sections) + 0.4 * _objective_alignment(req, sections))


# --------------------------------------------------------------------------- #
# Composition                                                                 #
# --------------------------------------------------------------------------- #


def _avg_skill_level(sections: list[dict]) -> float:
    """Average of the CV's numeric skill levels (0-100); 50.0 (neutral) if none."""
    levels: list[float] = []
    for s in sections:
        if "skill" not in _section_type(s):
            continue
        content = s.get("content")
        items = content.get("items") if isinstance(content, dict) else None
        if not isinstance(items, list):
            continue
        for it in items:
            if isinstance(it, dict) and isinstance(it.get("level"), int | float):
                lvl = float(it["level"])
                if 0.0 <= lvl <= 100.0:
                    levels.append(lvl)
    return sum(levels) / len(levels) if levels else 50.0


def score_cv(
    job: dict,
    req: _Requirements,
    cv: CvInput,
    *,
    stale_days: int,
    jd_ind: str | None = None,
) -> CvFit:
    cv_text_norm = grounding.normalize_expanded(grounding.sections_to_text(cv.sections))
    experience_norm = grounding.normalize_expanded(_section_text(cv.sections, _EXPERIENCE_TYPES))

    # Field distance (reused by EXPERIENCE title-relevance + CREDENTIALS major).
    # ``jd_ind`` is classified ONCE per job in ``evaluate`` and passed in (the JD is
    # identical across a user's CVs); ``cv_ind`` reuses the already-expanded
    # ``cv_text_norm`` instead of re-expanding the full CV text.
    if jd_ind is None:
        jd_ind = _jd_industry(job, req)
    cv_ind = _classify_industry_norm(cv_text_norm)
    field_score = _field_closeness(jd_ind, cv_ind)

    skills, matched_skills, skill_gaps = _skills_band(req, cv_text_norm, experience_norm)
    experience = _experience_band(req, job, cv.sections, cv_text_norm, field_score)
    scope = _scope_band(job, req, cv.sections, cv_text_norm)
    credentials, credential_matches, credential_gaps = _credentials_band(
        req, cv.sections, cv_text_norm, jd_ind
    )
    soft_skills = _soft_skills_band(job, cv.sections, cv_text_norm)
    trajectory = _trajectory_band(req, cv.sections)

    score = _clamp(
        W_SKILLS * skills
        + W_EXPERIENCE * experience
        + W_SCOPE * scope
        + W_CREDENTIALS * credentials
        + W_SOFT * soft_skills
        + W_TRAJECTORY * trajectory
    )

    # --- HR-realism competency gate ------------------------------------------
    # Core = "can they do THIS job at all" = skills + relevant experience. When the
    # JD specifies skills and this core is weak, the whole score is scaled down so a
    # wrong-field / no-skills candidate cannot be rescued by soft skills, tenure, or
    # credentials. A Nursing CV vs a DevSecOps JD has ~0 skills AND ~0 relevant
    # experience → the core collapses; a Full-Stack CV (same field, partial skills)
    # keeps far more of its score. A candidate with an adequate core is never gated.
    if req.required or req.preferred:
        core = 0.6 * skills + 0.4 * experience
        if core < _CORE_GATE_FLOOR:
            gate = _CORE_GATE_BASE + (1.0 - _CORE_GATE_BASE) * (core / _CORE_GATE_FLOOR)
            score = _clamp(score * gate)

    # Surfaced evidence is limited to curated inputs: the partner's structured skill
    # strings and structured credential requirements. Free-form JD prose never
    # reaches the user here.
    matched = _dedupe_terms([*matched_skills, *credential_matches], limit=16)
    gaps = _dedupe_terms([*skill_gaps, *credential_gaps], limit=16)

    # Language mismatch warning: soft signal, not a score penalty.
    cv_lang_required = str(job.get("cv_language_required") or "any").lower()
    if cv_lang_required not in ("any", "") and cv.language and cv.language != cv_lang_required:
        lang_label = "English" if cv_lang_required == "en" else "Tiếng Việt"
        gaps = _dedupe_terms([f"CV in {lang_label} preferred", *gaps], limit=16)

    return CvFit(
        cv_id=cv.cv_id,
        title=cv.title,
        score=score,
        bands=BandScores(
            skills=skills,
            experience=experience,
            scope=scope,
            credentials=credentials,
            soft_skills=soft_skills,
            trajectory=trajectory,
        ),
        matched_skills=matched,
        gaps=gaps,
        stale=cv.last_updated_days > stale_days,
        last_updated_days=cv.last_updated_days,
        avg_skill_level=_avg_skill_level(cv.sections),
    )


def evaluate(
    job: dict,
    cvs: list[CvInput],
    *,
    stale_days: int,
) -> JobFitOutcome:
    """Score + rank every CV for the job. Pure and deterministic.

    Cross-lingual (VN↔EN) skill matching is handled UPSTREAM of this function by
    ``app.ai.cv.skill_translation.english_augment``, which appends canonical-English
    forms of the JD and CV skill terms before invoking ``evaluate`` — so the
    deterministic lexical/ontology tier here does all the matching. Offline the
    augmentation is a no-op, so this function stays byte-for-byte identical to the
    pure lexical scorer and every existing lexical test passes unchanged.
    """

    req = resolve_requirements(job)
    # Classify the JD's field ONCE (identical across the user's CVs) and pass it in,
    # so ``score_cv`` doesn't re-expand + re-classify the JD per CV.
    jd_ind = _jd_industry(job, req)
    results = [score_cv(job, req, cv, stale_days=stale_days, jd_ind=jd_ind) for cv in cvs]
    # Rank: score first (authoritative), then higher self-rated proficiency as a
    # tie-breaker, then freshness, then id for a stable total order.
    results.sort(key=lambda r: (-r.score, -r.avg_skill_level, r.last_updated_days, r.cv_id))

    recommended_cv_id = results[0].cv_id if results else None
    signal = "low_signal" if req.count < 4 or req.used_fallback else "ok"
    return JobFitOutcome(
        results=results,
        recommended_cv_id=recommended_cv_id,
        signal=signal,
        requirement_count=req.count,
    )
