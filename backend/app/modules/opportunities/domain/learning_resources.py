"""Curated skill -> learning-resource catalog for student job intelligence.

When a student's CV is missing a skill a job requires, the job-intelligence
``learning_gaps`` block suggests a concrete, actionable way to close the gap.
Previously every gap returned the same generic ``practice_project`` sentence;
this module maps normalized gap-skill names to a **specific** resource type and a
tailored (i18n-safe) suggestion, with a truthful generic fallback for unknown
skills.

Design rules:
- Deterministic and pure (no I/O, no AI). The same skill always maps to the same
  resource — reproducible across requests.
- User-safe copy only. Suggestions never name a provider/model, a branded course,
  a certification vendor, or any AI internal — they describe an activity the
  student can do, not a product to buy.
- i18n-backed: every suggestion has ``vi`` (default) and ``en`` copy; ``{skill}``
  is interpolated with the ORIGINAL (display-cased) gap label so it reads
  naturally in the UI (which renders these strings raw).
- ``resource_type`` is a stable machine code (the frontend may icon/label it);
  the generic fallback keeps ``practice_project`` for backward compatibility with
  the documented default.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Resource templates: template_key -> (resource_type, {locale: suggestion})    #
# --------------------------------------------------------------------------- #
#
# ``{skill}`` is filled with the original gap label. Suggestions are phrased so
# the interpolated skill name reads naturally in either language.

_TEMPLATES: dict[str, tuple[str, dict[str, str]]] = {
    "containers": (
        "hands_on_lab",
        {
            "vi": (
                "Đóng gói một dự án hiện có của bạn bằng Dockerfile (và tệp "
                "compose) rồi ghi lại thiết lập {skill} trong CV để chứng minh "
                "kinh nghiệm thực hành."
            ),
            "en": (
                "Containerize one of your existing projects with a Dockerfile "
                "(and a compose file) and note the {skill} setup on your CV to "
                "show hands-on experience."
            ),
        },
    ),
    "cloud": (
        "certification_path",
        {
            "vi": (
                "Hoàn thành một lộ trình kiến thức nền tảng về điện toán đám mây "
                "và triển khai một dịch vụ nhỏ để có bằng chứng thực tế về {skill}."
            ),
            "en": (
                "Work through a foundational cloud path and deploy one small "
                "service to build real hands-on evidence for {skill}."
            ),
        },
    ),
    "sql": (
        "guided_dataset",
        {
            "vi": (
                "Luyện JOIN, hàm tổng hợp và truy vấn nâng cao {skill} trên một "
                "tập dữ liệu mẫu, rồi thêm một dự án phân tích nhỏ vào hồ sơ."
            ),
            "en": (
                "Practice JOINs, aggregation, and window queries in {skill} on a "
                "sample dataset, then add a small analysis project to your "
                "portfolio."
            ),
        },
    ),
    "programming": (
        "coding_exercises",
        {
            "vi": (
                "Hoàn thành một bộ bài tập lập trình {skill} và công bố một công "
                "cụ hoặc script nhỏ để thể hiện sự thành thạo."
            ),
            "en": (
                "Complete a set of {skill} coding exercises and publish a small "
                "script or CLI tool to evidence fluency."
            ),
        },
    ),
    "backend_framework": (
        "build_api",
        {
            "vi": (
                "Xây dựng một REST API nhỏ bằng {skill} (có xác thực và truy cập "
                "cơ sở dữ liệu) và đưa mã nguồn lên hồ sơ của bạn."
            ),
            "en": (
                "Build a small REST API with {skill} (with auth and a database "
                "layer) and put the source in your portfolio."
            ),
        },
    ),
    "frontend": (
        "portfolio_piece",
        {
            "vi": (
                "Dựng một giao diện nhỏ nhưng hoàn chỉnh bằng {skill} (responsive, "
                "có trạng thái rỗng/đang tải) và đưa vào hồ sơ năng lực."
            ),
            "en": (
                "Build one small but complete UI with {skill} (responsive, with "
                "empty/loading states) and add it to your portfolio."
            ),
        },
    ),
    "ml": (
        "foundations_course",
        {
            "vi": (
                "Học một khóa nền tảng về {skill} và hoàn thành một dự án thực "
                "hành từ dữ liệu thô đến kết quả để chứng minh năng lực."
            ),
            "en": (
                "Take a foundational {skill} course and finish one hands-on "
                "project from raw data to result to demonstrate capability."
            ),
        },
    ),
    "version_control": (
        "version_control_practice",
        {
            "vi": (
                "Thực hành quy trình {skill} theo nhánh (branch, pull request, "
                "review) trên một dự án công khai để thể hiện cách làm việc nhóm."
            ),
            "en": (
                "Practice a branch-based {skill} workflow (branches, pull "
                "requests, reviews) on a public project to show collaboration."
            ),
        },
    ),
    "soft_skill": (
        "experience_reflection",
        {
            "vi": (
                "Thêm một ví dụ cụ thể vào CV cho thấy bạn đã thể hiện {skill} với "
                "kết quả đo lường được."
            ),
            "en": (
                "Add a concrete example to your CV where you demonstrated {skill} "
                "with a measurable outcome."
            ),
        },
    ),
    "language": (
        "language_practice",
        {
            "vi": (
                "Luyện {skill} theo ngữ cảnh công việc (đọc tài liệu, viết mô tả "
                "dự án) và cập nhật trình độ trong CV khi bạn tiến bộ."
            ),
            "en": (
                "Practice {skill} in a work context (reading docs, writing "
                "project summaries) and update your CV level as you improve."
            ),
        },
    ),
}

# Generic fallback for an unknown skill — kept verbatim from the previous inline
# copy so unknown-skill behaviour is unchanged (``practice_project`` type).
_GENERIC: tuple[str, dict[str, str]] = (
    "practice_project",
    {
        "vi": (
            "Xây dựng một dự án nhỏ trong hồ sơ năng lực để chứng minh {skill}, "
            "hoặc thêm một dòng vào CV mô tả kinh nghiệm thực tế của bạn với kỹ "
            "năng này nếu bạn đã có."
        ),
        "en": (
            "Build a small portfolio project that demonstrates {skill}, or add a "
            "line to your CV describing real experience with it if you already "
            "have some."
        ),
    },
)

# --------------------------------------------------------------------------- #
# Normalized skill -> template key                                            #
# --------------------------------------------------------------------------- #

_SKILL_TEMPLATE: dict[str, str] = {
    # Containers / orchestration
    "docker": "containers",
    "kubernetes": "containers",
    "containerization": "containers",
    # Cloud
    "aws": "cloud",
    "gcp": "cloud",
    "azure": "cloud",
    "cloud": "cloud",
    "cloud computing": "cloud",
    # Databases / SQL
    "sql": "sql",
    "database": "sql",
    "databases": "sql",
    "data analysis": "sql",
    "pandas": "sql",
    # General-purpose programming languages
    "python": "programming",
    "javascript": "programming",
    "typescript": "programming",
    "java": "programming",
    "c++": "programming",
    "c#": "programming",
    "go": "programming",
    "golang": "programming",
    "rust": "programming",
    "algorithms": "programming",
    "data structures": "programming",
    # Backend frameworks
    "fastapi": "backend_framework",
    "django": "backend_framework",
    "flask": "backend_framework",
    "express": "backend_framework",
    "node": "backend_framework",
    "spring": "backend_framework",
    "spring boot": "backend_framework",
    "rest api": "backend_framework",
    # Frontend
    "react": "frontend",
    "vue": "frontend",
    "angular": "frontend",
    "next.js": "frontend",
    "html": "frontend",
    "css": "frontend",
    "tailwind": "frontend",
    "frontend": "frontend",
    "ui": "frontend",
    # ML / data science
    "machine learning": "ml",
    "deep learning": "ml",
    "data science": "ml",
    "statistics": "ml",
    "tensorflow": "ml",
    "pytorch": "ml",
    # Version control
    "git": "version_control",
    "github": "version_control",
    "gitlab": "version_control",
    # Soft skills
    "communication": "soft_skill",
    "teamwork": "soft_skill",
    "leadership": "soft_skill",
    "problem solving": "soft_skill",
    "problem-solving": "soft_skill",
    "collaboration": "soft_skill",
    "time management": "soft_skill",
    "presentation": "soft_skill",
    # Languages
    "english": "language",
    "ielts": "language",
    "toeic": "language",
}

# alias (normalized) -> canonical normalized skill in ``_SKILL_TEMPLATE``.
_ALIASES: dict[str, str] = {
    "k8s": "kubernetes",
    "postgres": "sql",
    "postgresql": "sql",
    "mysql": "sql",
    "sqlite": "sql",
    "mssql": "sql",
    "js": "javascript",
    "ts": "typescript",
    "reactjs": "react",
    "react.js": "react",
    "vuejs": "vue",
    "vue.js": "vue",
    "nodejs": "node",
    "node.js": "node",
    "nextjs": "next.js",
    "ml": "machine learning",
    "ai": "machine learning",
    "amazon web services": "aws",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
}


def _normalize(skill: str) -> str:
    """Lowercase + collapse internal whitespace for a stable lookup key."""

    return " ".join(skill.strip().lower().split())


def _lookup_template_key(skill: str) -> str | None:
    """Resolve a gap skill to a template key, or ``None`` for the generic fallback.

    Deterministic resolution order: exact normalized match, alias, then the
    first token (so ``"Python 3.11"`` still resolves to the ``python`` entry).
    No fuzzy/substring matching, so a lookup can never misfire between unrelated
    skills (e.g. ``java`` vs ``javascript``).
    """

    norm = _normalize(skill)
    if norm in _SKILL_TEMPLATE:
        return _SKILL_TEMPLATE[norm]
    if norm in _ALIASES:
        return _SKILL_TEMPLATE[_ALIASES[norm]]

    first = norm.split()[0] if norm else ""
    if first and first != norm:
        if first in _SKILL_TEMPLATE:
            return _SKILL_TEMPLATE[first]
        if first in _ALIASES:
            return _SKILL_TEMPLATE[_ALIASES[first]]
    return None


def resource_for(skill: str, *, locale: str = "vi") -> dict[str, str]:
    """Return ``{"resource_type", "suggestion"}`` for a gap skill.

    A curated skill returns its specific resource type + tailored suggestion; an
    unknown skill returns the generic ``practice_project`` fallback. The
    suggestion is localized (``vi`` default) with the original skill label
    interpolated.
    """

    key = _lookup_template_key(skill)
    resource_type, copy = _TEMPLATES[key] if key is not None else _GENERIC
    template = copy.get(locale) or copy["vi"]
    return {
        "resource_type": resource_type,
        "suggestion": template.format(skill=skill),
    }
