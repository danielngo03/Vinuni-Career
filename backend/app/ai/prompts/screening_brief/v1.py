"""AI prompt for partner candidate screening brief — v1.

Generates 3-4 structured bullet points summarising the candidate's CV
relative to the job requirements. Privacy-safe: no name/email/contact info
is included in the prompt. Output is advisory only; the recruiter makes
the final decision.
"""

PROMPT_VERSION = 1

STATIC_SYSTEM_PROMPT = """\
You are an impartial talent screening assistant helping a recruiter \
quickly understand whether a candidate matches an open role.

Rules:
1. Write exactly 3-4 concise bullet points (one sentence each).
2. Cover: (a) a key relevant skill or experience that matches the role, \
(b) another strength from the CV, (c) a notable gap or missing \
requirement if one exists, (d) overall suitability signal (strong / \
moderate / weak).
3. Base everything only on the structured CV data provided. \
Do NOT invent facts.
4. Do NOT reference the candidate's name, contact information, or any PII.
5. Keep each bullet under 25 words.
6. Return ONLY a JSON object:
   {"bullets": ["bullet 1", "bullet 2", "bullet 3", "bullet 4"],
    "suitability": "strong"|"moderate"|"weak"}
"""


def build_user_message(
    *,
    job_title: str,
    required_skills: list[str],
    candidate_skills: list[str],
    experience_titles: list[str],
    education_summary: str,
    cover_letter_snippet: str | None,
) -> str:
    parts = [f"Role: {job_title}"]
    if required_skills:
        parts.append("Required skills: " + ", ".join(required_skills[:12]))
    if candidate_skills:
        parts.append("Candidate skills: " + ", ".join(candidate_skills[:15]))
    if experience_titles:
        parts.append("Experience titles: " + ", ".join(experience_titles[:5]))
    if education_summary:
        parts.append(f"Education: {education_summary}")
    if cover_letter_snippet:
        parts.append(f"Cover letter excerpt: {cover_letter_snippet[:200]}")
    parts.append("\nWrite 3-4 screening bullet points comparing this candidate to the role.")
    return "\n".join(parts)
