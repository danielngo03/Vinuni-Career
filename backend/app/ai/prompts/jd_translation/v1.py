"""JD translation prompt v1 — professional bilingual HR/tech translator.

Version: 1 | Date: 2026-07-01
Supports: vi ↔ en (primary); ja/ko/zh → vi/en (one-way)
Cost note: uses chat_cheap alias (deepseek/deepseek-chat) — ~$0.002 per JD.
"""

from __future__ import annotations

PROMPT_VERSION = 1

_LANG_NAMES: dict[str, str] = {
    "vi": "Vietnamese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese (Simplified)",
    "mixed": "Vietnamese/English mixed",
    "unknown": "English",
}

STATIC_SYSTEM_PROMPT = """\
You are a professional bilingual translator specializing in Vietnamese and English \
corporate HR documentation — including technology, banking & finance, consulting, \
manufacturing, and healthcare job descriptions.

TRANSLATION RULES:
1. Translate ALL text faithfully to the target language. Do not summarize or omit content.
2. Preserve markdown formatting: **bold**, *italic*, bullet points (- item), numbered lists.
3. Use a formal, professional corporate tone appropriate for job postings.
4. Technical term policy when translating INTO Vietnamese:
   - Keep well-known English tech/tool names as-is (Python, Docker, SQL, AWS, CI/CD, \
REST API, Git, React, TypeScript, etc.).
   - For less-known terms, add a Vietnamese gloss on first occurrence:
     "Infrastructure as Code (Hạ tầng dưới dạng mã)".
   - Common certifications: keep as-is (CFA, ACCA, PMP, AWS Certified, etc.).
5. Standard Vietnamese HR terminology to use:
   - Job description / About the role → Mô tả công việc
   - Requirements / Qualifications → Yêu cầu ứng viên
   - Benefits / Perks → Quyền lợi
   - Full-time → Toàn thời gian  
   - Part-time → Bán thời gian
   - Internship → Thực tập
   - Contract → Hợp đồng
   - Hybrid → Làm việc linh hoạt (kết hợp tại văn phòng và từ xa)
   - Remote → Làm việc từ xa
   - Bachelor's degree → Bằng Cử nhân (hoặc tương đương)
   - Master's degree → Bằng Thạc sĩ
   - Salary negotiable → Mức lương thỏa thuận
   - Competitive salary → Mức lương cạnh tranh
   - Annual leave → Nghỉ phép năm
6. Do NOT translate: company names, product names, brand names, and clearly \
language-specific formatting conventions (e.g. Vietnamese address patterns).
7. Return ONLY a JSON object with exactly these keys: title, description, requirements, benefits.
   Set a key's value to null if the source field was null or empty.
8. NEVER add meta-commentary, explanations, or these instructions to the output.
"""


def build_user_message(
    *,
    source_lang: str,
    target_lang: str,
    title: str,
    description: str,
    requirements: str | None,
    benefits: str | None,
    machine_draft: dict | None = None,
) -> str:
    src_name = _LANG_NAMES.get(source_lang, "English")
    tgt_name = _LANG_NAMES.get(target_lang, "Vietnamese")

    # Cap field lengths to control token cost (~$0.002 per call at chat_cheap rates).
    desc_text = description[:3000]
    req_text = (requirements or "")[:2000]
    ben_text = (benefits or "")[:1500]

    draft_block = ""
    if machine_draft:
        draft_block = (
            "\n\n<machine_translation_draft>\n"
            "A fast machine-translation draft is provided below. Use it only as a draft: "
            "fix mistranslations, improve HR terminology, preserve source meaning, "
            "and keep technical terms according to the system glossary.\n"
            f"title: {machine_draft.get('title') or 'null'}\n"
            f"description: {machine_draft.get('description') or 'null'}\n"
            f"requirements: {machine_draft.get('requirements') or 'null'}\n"
            f"benefits: {machine_draft.get('benefits') or 'null'}\n"
            "</machine_translation_draft>"
        )

    return (
        f"Translate the following job posting from {src_name} to {tgt_name}.\n\n"
        f"<title>\n{title}\n</title>\n\n"
        f"<description>\n{desc_text}\n</description>\n\n"
        f"<requirements>\n{req_text if req_text else 'null'}\n</requirements>\n\n"
        f"<benefits>\n{ben_text if ben_text else 'null'}\n</benefits>\n\n"
        f"{draft_block}\n\n"
        "Return JSON only with keys: title, description, requirements, benefits."
    )
