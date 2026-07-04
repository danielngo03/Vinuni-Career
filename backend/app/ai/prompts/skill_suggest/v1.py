"""AI prompt for skill suggestions — v1.

Returns a JSON object with a list of skill names the student likely has
based on their major, experience, and existing skill set.
"""

PROMPT_VERSION = 1

STATIC_SYSTEM_PROMPT = """\
You are a career advisor helping university students build strong skill profiles.

Rules:
1. Suggest 6-8 skills the student is very likely to have given their major, \
experience titles, and existing skills.
2. Suggest only skills NOT already in the existing_skills list.
3. Prefer concrete, searchable skill names (e.g. "Python", "React", \
"Financial Modeling", "Data Analysis") over generic ones (e.g. "teamwork").
4. Lean toward skills commonly taught in the student's major or used \
in roles similar to their experience.
5. Return ONLY a JSON object in the format: \
{"suggestions": ["Skill 1", "Skill 2", ...]}
6. Do not invent fictitious certifications or tools not associated with \
the student's field.
"""


def build_user_message(
    *,
    major: str,
    headline: str,
    experience_titles: list[str],
    existing_skills: list[str],
) -> str:
    parts = []
    if major:
        parts.append(f"Major/field of study: {major}")
    if headline:
        parts.append(f"Profile headline: {headline}")
    if experience_titles:
        parts.append("Experience titles: " + ", ".join(experience_titles[:5]))
    if existing_skills:
        parts.append(
            "Skills already added (do NOT suggest these): " + ", ".join(existing_skills[:30])
        )
    else:
        parts.append("Skills already added: (none yet)")
    parts.append("\nSuggest 6-8 skills this student likely has but hasn't added yet.")
    return "\n".join(parts)
