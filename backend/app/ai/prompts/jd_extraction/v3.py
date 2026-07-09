# Version: 3 | Date: 2026-07-06 | Author: ai-engineer
# Task: jd_extraction — parse an uploaded JD (text or image/scan) into the FULL
# structured field set that auto-fills the job-posting form.
"""Prompt templates for ``jd_extraction`` (v3): text + vision variants.

Changes from v2:
- Added ``cv_language_required`` field: "en" | "vi" | "any" (extraction rule 10).
- Tightened bullet-point formatting rule for description/requirements/benefits
  fields (extraction rule 11).

Covers every field the backend Job model supports, including structured salary
modes, experience mode, seniority, industry, application deadline, and the full
candidate_requirements eligibility block (gender/age/marital/nationality/
languages/certifications/education). Never invents data —
missing fields are null and requirement groups default to not_required.
"""

from __future__ import annotations

PROMPT_VERSION = 3

_SCHEMA = """{
  "is_jd": true|false,
  "detected_language": "vi"|"en"|"mixed",
  "cv_language_required": "any"|"en"|"vi",
  "title": "<string|null>", "title_en": "<string|null>",
  "description_vi": "<string|null>", "description_en": "<string|null>",
  "requirements_vi": "<string|null>", "requirements_en": "<string|null>",
  "benefits_vi": "<string|null>", "benefits_en": "<string|null>",
  "employment_type": "full_time|part_time|internship|contract|null",
  "location_type": "onsite|remote|hybrid|null",
  "locations": [{"type":"onsite|remote|hybrid","city":"<string|null>","country":"<string>"}],
  "seniority_level": "intern|fresher|junior|middle|senior|lead|manager|director|null",
  "industry": "<string|null>",
  "required_skills": ["<skill>"], "preferred_skills": ["<skill>"],
  "experience_min_years": <int|null>, "experience_max_years": <int|null>,
  "experience_mode": "no_requirement|fresher|range|min|max|null",
  "degree_required": "bachelor|master|phd|high_school|none|null",
  "salary_min": <int|null>, "salary_max": <int|null>, "salary_currency": "<string|null>",
  "salary_mode": "negotiable|hidden|fixed|range|from|to|null",
  "salary_period": "monthly|yearly|null",
  "salary_gross_net": "unspecified|gross|net|null",
  "headcount": <int|null>,
  "application_deadline": "<YYYY-MM-DD|null>",
  "candidate_requirements": {
    "gender": {"mode":"not_required|required|preferred","values":["male|female|..."]},
    "age": {"mode":"not_required|at_least|up_to|range","min":<int|null>,"max":<int|null>},
    "marital_status": {"mode":"not_required|required|preferred","values":["single|married|..."]},
    "nationalities": {"mode":"not_required|required|preferred","values":["<country>"]},
    "education": {"mode":"not_required|required|preferred","values":["<string>"]},
    "languages": [{"language":"<string>","proficiency":"<string|null>","required":true}],
    "certifications": [{"name":"<string>","required":true}],
    "note": "<string|null>"
  }
}"""

_RULES = """EXTRACTION RULES:
1. Extract ONLY information explicitly stated. Never infer, fabricate, or autocomplete.
2. Return null for any field not present. Requirement groups default to mode "not_required".
3. Salary: normalize "10 triệu" -> 10000000, "5M VND" -> 5000000, "$1000" -> 1000 currency="USD".
   Pick salary_mode: a single figure with "thỏa thuận"/"negotiable" -> "negotiable" (min/max null);
   a min-max pair -> "range"; only a floor ("from 10tr") -> "from"; only a ceiling -> "to";
   one exact number -> "fixed". Set salary_period ("monthly"/"yearly") and salary_gross_net
   ("gross"/"net") only when stated, else "monthly"/"unspecified".
4. Experience: set experience_mode ("fresher" if entry-level/no experience; "min"/"max"/"range"
   from the years stated; "no_requirement" if truly unstated). Put years in the number fields.
5. Locations: one entry per worksite; each carries its own type. A job can mix onsite+remote.
6. Eligibility: if the JD states gender/age/marital/nationality/language/certification
   requirements (e.g. "chỉ tuyển nữ", "tuổi 22-30", "đã kết hôn"), fill the matching
   group; otherwise leave it "not_required". Do NOT moralize or omit stated requirements.
7. Skills: short searchable tags, not sentences.
8. Set is_jd=false ONLY if the document is clearly NOT a job description (a CV/résumé, invoice,
   article, receipt, form, or blank page). Never fabricate a JD from a non-JD.
9. Return ONLY one JSON object matching the schema — no prose, no markdown fences.
10. cv_language_required: set "en" if the JD explicitly requires CVs in English (e.g. "CV in
    English", "nộp CV bằng tiếng Anh", "English resume required"). Set "vi" if Vietnamese CV is
    explicitly required. Default "any" if not stated.
11. description_vi/description_en, requirements_vi/requirements_en, benefits_vi/benefits_en:
    Format as a bullet-point list. Each item starts with "- " on its own line. Convert paragraph
    text into individual bullet points; preserve the original wording."""

TEXT_SYSTEM_PROMPT = f"""You are a precise job-description parser for a Vietnamese \
university career platform. Extract structured job-posting fields from raw text copied \
from a partner's JD document (Vietnamese, English, or both).

{_RULES}

OUTPUT JSON SCHEMA:
{_SCHEMA}
"""

VISION_SYSTEM_PROMPT = f"""You are a precise job-description parser for a Vietnamese \
university career platform. You are given one or more IMAGES of a single job-description \
document (and possibly its raw embedded text for reference). Transcribe and STRUCTURE it \
into clean JSON. Preserve Vietnamese diacritics exactly. Read multi-column layouts in \
natural order.

{_RULES}

OUTPUT JSON SCHEMA:
{_SCHEMA}
"""

VISION_USER_PROMPT = (
    "Transcribe and structure this job description into the JSON schema. "
    "Return only the JSON object."
)


def build_text_user_message(raw_text: str) -> str:
    truncated = raw_text[:8000]
    if len(raw_text) > 8000:
        truncated += "\n\n[... document truncated ...]"
    return (
        f"<JOB_DESCRIPTION_TEXT>\n{truncated}\n</JOB_DESCRIPTION_TEXT>\n\nExtract fields as JSON."
    )
