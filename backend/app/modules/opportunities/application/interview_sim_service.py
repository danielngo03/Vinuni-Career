"""Interview Simulator AI service — generates tailored interview questions.

Student-facing, read-only advisory output (docs/AI_PRODUCT_SPEC.md §3 table).
No stored row — questions are ephemeral session artifacts for self-preparation.

Permission: authenticated student (any authenticated non-partner, non-admin may
call); the target job must be publicly visible.

Rules:
- No provider/model/token internals in the response.
- Output is JSON structured (list of questions + prep tips), not free text.
- Input guard runs on any free-text student instruction before the LLM call.
- The job must exist and be publicly visible (treats missing/private as 404).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cv.llm import generate_json_note
from app.ai.prompts.answer_feedback import v1 as feedback_prompt
from app.ai.prompts.interview_sim import v1 as sim_prompt
from app.ai.safety.input_guard import sanitize_instruction
from app.modules.opportunities.domain.lifecycle import visible_levels_for
from app.modules.opportunities.domain.models import Job
from app.modules.organization.application import org_reporting_facade
from app.shared.exceptions import AIUnavailableError, ResourceNotFoundError

_TASK_TYPE = "interview_sim"
_FEEDBACK_TASK_TYPE = "answer_feedback"
_MAX_TOKENS = 2000
_FEEDBACK_MAX_TOKENS = 500

_STATIC_FALLBACK_QUESTIONS = [
    {
        "number": 1,
        "type": "motivation",
        "question": "Why are you interested in this role and company?",
        "hint": "Interviewers look for genuine curiosity and research into the role.",
        "rubric": "A strong answer connects the candidate's goals to the specific role.",
    },
    {
        "number": 2,
        "type": "behavioral",
        "question": "Tell me about a time you faced a challenging deadline. How did you handle it?",
        "hint": "Interviewers look for structured thinking and ownership.",
        "rubric": "A strong answer uses the STAR method and shows measurable impact.",
    },
    {
        "number": 3,
        "type": "behavioral",
        "question": (
            "Describe a situation where you had to collaborate with a difficult team member."
        ),
        "hint": "Interviewers assess conflict resolution and communication.",
        "rubric": "A strong answer shows empathy, professionalism, and a positive outcome.",
    },
    {
        "number": 4,
        "type": "situational",
        "question": "How would you handle receiving critical feedback on your work?",
        "hint": "Interviewers look for growth mindset and emotional maturity.",
        "rubric": "A strong answer shows active listening and concrete follow-up steps.",
    },
    {
        "number": 5,
        "type": "motivation",
        "question": "Where do you see yourself in 3-5 years, and how does this role fit?",
        "hint": "Interviewers assess ambition, realism, and alignment with the company.",
        "rubric": "A strong answer is specific and ties personal growth to the role's path.",
    },
]

_STATIC_FALLBACK = {
    "questions": _STATIC_FALLBACK_QUESTIONS,
    "prep_tips": (
        "Review the job description carefully and prepare a STAR story for each "
        "responsibility. Research the company's recent projects and culture. "
        "Practice concise answers: aim for 1-2 minutes per response."
    ),
    "is_fallback": True,
}


async def generate_interview_prep(
    session: AsyncSession,
    *,
    principal,
    job_id: uuid.UUID,
    num_questions: int = 6,
    student_instruction: str | None = None,
    locale: str = "vi",
) -> dict:
    """Generate tailored interview questions for a publicly visible job.

    Returns a dict with ``questions``, ``prep_tips``, and ``prompt_version``.
    Falls back to static bank questions on AI failure (never raises on AI error).
    """
    # Load publicly visible job (students can only prep for public jobs)
    job = (
        await session.execute(
            select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError()

    levels = visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    now = __import__("datetime").datetime.utcnow()
    is_public = (
        job.status == "published"
        and job.published_at is not None
        and job.published_at <= now
        and (job.application_deadline is None or job.application_deadline >= now)
        and job.visibility in levels
    )
    if not is_public and not principal.is_superadmin:
        raise ResourceNotFoundError()

    # Load company name for context
    org = await org_reporting_facade.summary_for(session, job.org_id)

    # Sanitize optional student instruction
    extra_context: str | None = None
    if student_instruction:
        clean, _ = sanitize_instruction(student_instruction[:500])
        extra_context = clean or None

    num_questions = max(3, min(10, num_questions))

    inputs: dict = {
        "title": job.title,
        "company_name": org.display_name if org else None,
        "description": job.description,
        "required_skills": job.required_skills or [],
        "num_questions": num_questions,
    }
    if extra_context:
        inputs["student_profile"] = extra_context

    try:
        result = await generate_json_note(
            task_type=_TASK_TYPE,
            system_prompt=sim_prompt.STATIC_SYSTEM_PROMPT,
            user_content=sim_prompt.build_user_message(inputs),
            temperature=0.5,
            max_tokens=_MAX_TOKENS,
        )
        return normalize_interview_prep_result(result)
    except AIUnavailableError:
        return dict(_STATIC_FALLBACK)


def normalize_interview_prep_result(result: dict) -> dict:
    """Validate a raw LLM interview-prep JSON into the safe response shape.

    Pure function (no I/O). Raises :class:`AIUnavailableError` when the
    model produced zero usable questions (a non-dict/empty response) so the
    caller degrades to the static question bank rather than returning an
    empty prep session.
    """
    questions = result.get("questions") or []
    prep_tips = result.get("prep_tips") or ""
    clean_questions = []
    for i, q in enumerate(questions[:10]):
        if not isinstance(q, dict):
            continue
        clean_questions.append({
            "number": i + 1,
            "type": q.get("type", "behavioral"),
            "question": str(q.get("question", ""))[:500],
            "hint": str(q.get("hint", ""))[:300],
            "rubric": str(q.get("rubric", ""))[:300],
        })
    if not clean_questions:
        raise AIUnavailableError()
    return {
        "questions": clean_questions,
        "prep_tips": str(prep_tips)[:600],
        "prompt_version": sim_prompt.PROMPT_VERSION,
        "is_fallback": False,
    }


_FALLBACK_FEEDBACK = {
    "score": 3,
    "praise": "Your answer shows some relevant thinking about the topic.",
    "improve": (
        "Consider using the STAR method (Situation, Task, Action, Result) to make your answer more "
        "structured and concrete."
    ),
    "hint": (
        "Try including a specific example from your experience and quantify the outcome where "
        "possible."
    ),
    "is_fallback": True,
}


async def evaluate_answer(
    session: AsyncSession,
    *,
    principal,
    job_id: uuid.UUID,
    question: str,
    question_type: str,
    rubric: str,
    answer: str,
) -> dict:
    """Evaluate a student's interview answer and return coaching feedback.

    The job must be publicly visible. Output is ephemeral advisory — never stored,
    never shown to the partner. Falls back to static guidance on AI failure.

    Returns: score (1-5), praise, improve, hint, is_fallback, prompt_version.
    """
    # Permission: authenticated non-partner student
    if principal.persona not in ("student", None) and not principal.is_superadmin:
        from app.shared.exceptions import PermissionDeniedError
        raise PermissionDeniedError()

    # Verify job is publicly accessible (reuse existing check path)
    job = (
        await session.execute(
            select(Job).where(Job.id == job_id, Job.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if job is None:
        raise ResourceNotFoundError()

    levels = visible_levels_for(
        principal.persona, is_authenticated=principal.is_authenticated
    )
    now = __import__("datetime").datetime.utcnow()
    is_public = (
        job.status == "published"
        and job.published_at is not None
        and job.published_at <= now
        and (job.application_deadline is None or job.application_deadline >= now)
        and job.visibility in levels
    )
    if not is_public and not principal.is_superadmin:
        raise ResourceNotFoundError()

    # Sanitize student answer (could contain injection attempts)
    clean_answer, _ = sanitize_instruction(answer[:600])
    clean_question, _ = sanitize_instruction(question[:400])
    clean_rubric, _ = sanitize_instruction(rubric[:300])

    inputs = {
        "question_type": question_type or "behavioral",
        "question": clean_question or question[:400],
        "rubric": clean_rubric or rubric[:300],
        "answer": clean_answer or "",
    }

    try:
        result = await generate_json_note(
            task_type=_FEEDBACK_TASK_TYPE,
            system_prompt=feedback_prompt.STATIC_SYSTEM_PROMPT,
            user_content=feedback_prompt.build_user_message(inputs),
            temperature=0.3,
            max_tokens=_FEEDBACK_MAX_TOKENS,
        )
        return normalize_answer_feedback_result(result)
    except AIUnavailableError:
        return dict(_FALLBACK_FEEDBACK)


def normalize_answer_feedback_result(result: dict) -> dict:
    """Validate a raw LLM answer-feedback JSON into the safe response shape.

    Pure function (no I/O). ``score`` is clamped to 1-5; a hallucinated
    non-numeric score (e.g. ``"five"``) previously raised an uncaught
    ``ValueError`` all the way out of ``evaluate_answer`` instead of
    degrading gracefully like every other AI task in this module — fixed
    here by catching the conversion error and defaulting to a neutral score.
    """
    raw_score = result.get("score")
    try:
        score = int(raw_score) if raw_score is not None else 3
    except (TypeError, ValueError):
        score = 3
    score = max(1, min(5, score))
    praise = str(result.get("praise") or "")[:400]
    improve = str(result.get("improve") or "")[:400]
    hint = str(result.get("hint") or "")[:300]
    if not praise and not improve:
        raise AIUnavailableError()
    return {
        "score": score,
        "praise": praise,
        "improve": improve,
        "hint": hint,
        "prompt_version": feedback_prompt.PROMPT_VERSION,
        "is_fallback": False,
    }
