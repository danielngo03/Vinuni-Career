"""AI prompt for student profile summary draft — v1.

Generates a 2-3 sentence professional "About you" paragraph for the student's
profile based on their academic background, experience, and skills.
"""

PROMPT_VERSION = 1

STATIC_SYSTEM_PROMPT = """\
You are a career advisor helping a university student write their professional \
profile summary.

Rules:
1. Write exactly 2-3 sentences in first person (start with "I am" or "I'm" or \
the student's name when provided).
2. Highlight the student's field of study, ambitions, and one or two \
relevant skills or experience highlights.
3. Keep the tone professional yet personable — suitable for a recruiter's \
first impression.
4. Do NOT invent specific companies, projects, GPAs, awards, or quantified \
outcomes not mentioned in the input.
5. Return ONLY the summary paragraph text. No labels, no headings, no \
extra explanation.
6. Write in English unless the student's data is primarily in Vietnamese, \
in which case you may respond in Vietnamese.
"""


def build_user_message(
    *,
    name: str,
    major: str,
    degree_level: str,
    headline: str,
    experience_titles: list[str],
    skills: list[str],
) -> str:
    parts = []
    if name:
        parts.append(f"Student name: {name}")
    if major:
        parts.append(f"Major: {major}")
    if degree_level:
        parts.append(f"Degree level: {degree_level}")
    if headline:
        parts.append(f"Headline: {headline}")
    if experience_titles:
        parts.append("Experience titles: " + ", ".join(experience_titles[:4]))
    if skills:
        parts.append("Key skills: " + ", ".join(skills[:10]))
    parts.append("\nWrite a 2-3 sentence professional profile summary.")
    return "\n".join(parts)
