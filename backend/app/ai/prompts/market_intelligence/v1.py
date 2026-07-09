# Version: 1 | Date: 2026-07-02 | Author: ai-engineer
# Change: initial market-intelligence narrative prompt (aggregate-grounded)
# Previous: none
"""Market intelligence narrative prompt — v1.

Summarises PRE-COMPUTED, AGGREGATE-ONLY hiring statistics for university
career-services staff (permission_class ``restricted_admin``). The model never
sees individual students, applications, partners-by-name beyond counts, or any
PII — only the aggregate report dict rendered below. Fabricating numbers is
forbidden: every figure in the narrative must come from the provided data.
"""

PROMPT_VERSION = 1

STATIC_SYSTEM_PROMPT = """\
You are a labor-market analyst writing a short internal briefing for a
university career-services team.

Rules:
1. Use ONLY the aggregate statistics provided. Never invent, extrapolate, or
   round numbers into claims the data does not support.
2. Write 3-5 short sentences: overall hiring volume and its 30-day trend,
   the dominant employment types, the most in-demand skills, and one
   actionable observation for career advisors.
3. Neutral, factual tone. No marketing language, no advice to individual
   students, no mention of any individual person or single company.
4. If the data is sparse (few or zero jobs), say so plainly and recommend
   collecting more postings before drawing conclusions.
5. Output plain text only — no markdown, no JSON, no headers.
"""


def build_user_message(report: dict) -> str:
    lines = ["Aggregate hiring statistics:"]
    lines.append(f"- Active published jobs: {report.get('active_jobs', 0)}")
    lines.append(
        f"- Jobs published in the last 30 days: {report.get('jobs_last_30d', 0)} "
        f"(previous 30 days: {report.get('jobs_prev_30d', 0)}, "
        f"trend: {report.get('trend', 'flat')})"
    )
    for et in report.get("employment_types", [])[:5]:
        lines.append(f"- Employment type {et['type']}: {et['count']} jobs")
    top_skills = report.get("top_skills", [])[:10]
    if top_skills:
        lines.append(
            "- Most-demanded skills: "
            + ", ".join(f"{s['skill']} ({s['count']})" for s in top_skills)
        )
    lines.append(f"- Salary disclosure rate: {report.get('salary_disclosure_rate', 0)}%")
    lines.append("\nWrite the 3-5 sentence briefing now.")
    return "\n".join(lines)
