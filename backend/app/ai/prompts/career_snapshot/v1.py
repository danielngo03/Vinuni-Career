"""AI prompt: personalized student career snapshot (v1).

Generates a 2-3 sentence first-person encouragement summary of the student's
current job search status. Tone: supportive, honest, actionable.
No PII beyond what is passed in; no company/recruiter names.
"""

PROMPT_VERSION = 1

STATIC_SYSTEM_PROMPT = """You are a career advisor writing a brief, honest, encouraging \
snapshot for a student's job search.

Rules:
1. Write 2-3 sentences in second-person ("You have…", "Consider…").
2. Mention their activity level (applications sent, interviews) factually.
3. If they have no activity, gently encourage first steps.
4. Be supportive and specific — not generic motivational filler.
5. No company names, recruiter names, or PII.
6. Do not invent facts. Only use the data provided.
7. Return ONLY the paragraph — no labels, no markdown, no preamble."""


def build_user_message(
    *,
    total_applications: int,
    active_applications: int,
    interviews_upcoming: int,
    offers_pending: int,
    most_recent_status: str | None,
    open_to_work: bool,
    headline: str | None,
) -> str:
    parts = [
        f"Applications sent: {total_applications}",
        f"Active (not rejected/withdrawn): {active_applications}",
        f"Upcoming interviews: {interviews_upcoming}",
        f"Pending offers: {offers_pending}",
        f"Most recent application status: {most_recent_status or 'none'}",
        f"Open to work: {open_to_work}",
        f"Student headline: {headline or 'not set'}",
    ]
    return "\n".join(parts)
