"""Tool specs registry — declares every tool the AI assistant may call.

Contains only the ToolSpec dataclass and the TOOL_SPECS dict.
No database access or business logic here.

Every ``ToolSpec`` instance carries the full AI_PRODUCT_SPEC.md §7 tool
registry contract fields (permission_class, persona, required_permissions,
input_schema, side_effects, confirmation_copy, audit_event_type,
fallback_behavior, max_retries, timeout_seconds). ``__post_init__`` enforces
the §7/§4.3 invariant that every ``confirmation_required`` tool declares
``confirmation_copy`` and an ``audit_event_type`` — this is checked at import
time (and in ``tests/unit/test_ai_governance.py``) so a new mutating tool
cannot silently ship without a confirmation card or an audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Personas that may see/invoke assistant tools. Kept as plain strings (not an
# enum) so new personas can be added without a migration; RBAC enforcement
# itself lives in the tool handler / service layer, not here.
STUDENT = "student"
PARTNER_USER = "partner_user"
UNIVERSITY_STAFF = "university_staff"

_ALL_AUTHENTICATED = [STUDENT, PARTNER_USER, UNIVERSITY_STAFF]


@dataclass(frozen=True)
class ConfirmationCopy:
    """Locale-driven confirmation-card copy for a mutating tool (§4.3).

    The tool contract must NOT hardcode a single locale. Instead of literal
    strings this stores message-catalog KEYS resolved at render time through the
    existing assistant i18n mechanism (``ai_assistant.application.messages``),
    so the confirmation card renders vi/en (and any future locale) from one
    contract. Use :meth:`localized` to materialise the four user-facing strings
    for a given locale.
    """

    title_key: str
    body_key: str
    cta_confirm_key: str
    cta_cancel_key: str = "confirm.card.cta_cancel"

    def localized(self, locale: str | None = None) -> dict[str, str]:
        """Resolve the card's title/body/CTAs for ``locale`` (vi/en fallback vi)."""
        # Imported lazily to avoid a module-load import cycle (messages.py has no
        # dependency on the tool specs, but specs.py is imported very early).
        from app.modules.ai_assistant.application.messages import assistant_message

        return {
            "title": assistant_message(self.title_key, locale),
            "body": assistant_message(self.body_key, locale),
            "cta_confirm": assistant_message(self.cta_confirm_key, locale),
            "cta_cancel": assistant_message(self.cta_cancel_key, locale),
        }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict  # input_schema (JSON Schema)
    permission_class: str  # read_only | confirmation_required
    fallback: str  # fallback_behavior — what to tell the user when the tool/AI fails
    persona: list[str] = field(default_factory=lambda: list(_ALL_AUTHENTICATED))
    required_permissions: list[str] = field(default_factory=lambda: ["authenticated"])
    output_schema: dict | None = None
    side_effects: list[str] | None = None
    confirmation_copy: ConfirmationCopy | None = None
    audit_event_type: str = ""
    max_retries: int = 0
    timeout_seconds: int = 15

    def __post_init__(self) -> None:
        if not self.audit_event_type:
            raise ValueError(f"ToolSpec {self.name!r} must declare audit_event_type (§7)")
        if self.permission_class == "confirmation_required":
            if self.confirmation_copy is None:
                raise ValueError(
                    f"ToolSpec {self.name!r} is confirmation_required and must declare "
                    "confirmation_copy (§4.3)"
                )
            if not self.side_effects:
                raise ValueError(
                    f"ToolSpec {self.name!r} is confirmation_required and must declare "
                    "side_effects (§7)"
                )


TOOL_SPECS: dict[str, ToolSpec] = {
    "search_jobs": ToolSpec(
        name="search_jobs",
        description=(
            "Search for job listings on the platform. Returns a list of up to 5 relevant jobs with "
            "title, company, location, and a link. Use this when the student asks to find jobs, "
            "browse opportunities, or wants to know what positions are available."
        ),
        parameters={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search keywords"},
                "province_code": {
                    "type": "string",
                    "description": "Province code, e.g. HN for Hanoi",
                },
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "jobs": {"type": "array", "items": {"type": "object"}},
            },
        },
        permission_class="read_only",
        persona=[STUDENT],
        fallback="I couldn't search jobs right now. You can browse jobs at /jobs.",
        audit_event_type="TOOL_SEARCH_JOBS",
    ),
    "get_my_applications": ToolSpec(
        name="get_my_applications",
        description=(
            "Get the student's own recent job applications. Returns up to 5 recent applications "
            "with job title, company, status, and when they applied. Use this when the student "
            "asks about their applications, application status, or what jobs they've applied to."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback="I couldn't retrieve your applications right now. Check /student/applications.",
        audit_event_type="TOOL_GET_MY_APPLICATIONS",
    ),
    "get_my_cvs": ToolSpec(
        name="get_my_cvs",
        description=(
            "Get the student's CV library summary — list of CVs with title, status, and last "
            "edited date. Use this when the student asks about their CVs, which CV to use, or "
            "wants to manage their CV library."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback="I couldn't retrieve your CVs right now. Check /student/cv.",
        audit_event_type="TOOL_GET_MY_CVS",
    ),
    "get_upcoming_events": ToolSpec(
        name="get_upcoming_events",
        description=(
            "Get upcoming career events, workshops, and fairs on the platform. Returns up to 4 "
            "upcoming events with name, type, date, and format. Use this when the student asks "
            "about events, career fairs, workshops, or networking."
        ),
        parameters={
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "enum": ["career_fair", "workshop", "info_session", "networking", "webinar"],
                    "description": "Filter by event type",
                },
            },
            "required": [],
        },
        permission_class="read_only",
        fallback="I couldn't load events right now. Browse events at /events.",
        audit_event_type="TOOL_GET_UPCOMING_EVENTS",
    ),
    "get_saved_jobs": ToolSpec(
        name="get_saved_jobs",
        description=(
            "Get the student's saved/bookmarked jobs. Returns up to 5 saved jobs with title, "
            "company, and status. Use this when the student asks about their saved jobs, "
            "bookmarked jobs, or wants to review their job watchlist."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback="I couldn't retrieve your saved jobs right now. Check /student/saved-jobs.",
        audit_event_type="TOOL_GET_SAVED_JOBS",
    ),
    "get_profile_status": ToolSpec(
        name="get_profile_status",
        description=(
            "Get the student's identity-profile status. Returns whether the student is marked "
            "'open to work' (the profile's only career signal — all career detail lives in the "
            "student's CVs). Use this when the student asks about their open-to-work status or "
            "their visibility to recruiters; for career content, point them to their CVs."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback=(
            "I couldn't check your profile status right now. Visit your profile at "
            "/student/profile."
        ),
        audit_event_type="TOOL_GET_PROFILE_STATUS",
    ),
    "get_job_alerts": ToolSpec(
        name="get_job_alerts",
        description=(
            "Get the student's active job alert subscriptions. Returns up to 10 alerts with name, "
            "keywords, employment type, work mode, and when they were last triggered. Use this "
            "when the student asks about their job alert subscriptions, notification settings, or "
            "wants to know what job searches they have saved."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback="I couldn't retrieve your job alerts right now. Manage them at /student/alerts.",
        audit_event_type="TOOL_GET_JOB_ALERTS",
    ),
    "get_upcoming_interviews": ToolSpec(
        name="get_upcoming_interviews",
        description=(
            "Get the student's upcoming scheduled interviews. Returns interviews with job title, "
            "company, interview mode, scheduled time, and location/link. Use this when the student "
            "asks about interviews, their schedule, when their next interview is, or how to "
            "prepare for an upcoming interview."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback=(
            "I couldn't retrieve your interviews right now. Check /student/applications for your "
            "interview details."
        ),
        audit_event_type="TOOL_GET_UPCOMING_INTERVIEWS",
    ),
    "search_companies": ToolSpec(
        name="search_companies",
        description=(
            "Search for partner companies and employers on the platform. Returns up to 5 companies "
            "with name, industry, and number of open roles. Use this when the student asks about "
            "specific companies, wants to research employers, or asks which companies are hiring."
        ),
        parameters={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Company name or industry keyword"},
                "industry": {
                    "type": "string",
                    "description": "Industry filter, e.g. 'technology', 'finance'",
                },
            },
            "required": [],
        },
        permission_class="read_only",
        fallback="I couldn't search companies right now. Browse companies at /companies.",
        audit_event_type="TOOL_SEARCH_COMPANIES",
    ),
    "get_company_reviews": ToolSpec(
        name="get_company_reviews",
        description=(
            "Get the public company review summary and recent reviews for a specific company. "
            "Returns the overall rating, category scores (culture, management, work-life balance, "
            "compensation, growth), and up to 3 recent published reviews. Use this when the "
            "student asks about a company's reputation, employee experience, culture, or wants to "
            "know what people think about working there."
        ),
        parameters={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": (
                        "Company slug from a prior search_companies result, e.g. 'vingroup'"
                    ),
                },
            },
            "required": ["slug"],
        },
        permission_class="read_only",
        fallback=(
            "I couldn't load company reviews right now. Check the company page on the platform for "
            "reviews."
        ),
        audit_event_type="TOOL_GET_COMPANY_REVIEWS",
    ),
    "get_job_detail": ToolSpec(
        name="get_job_detail",
        description=(
            "Get detailed information about a specific job posting. Returns the full job "
            "description, requirements, benefits, salary range (if disclosed), application "
            "deadline, and required skills. Use this when the student wants to know more about a "
            "specific job they found via search_jobs, or when they ask for details about a "
            "particular position."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job UUID from a prior search_jobs result",
                },
            },
            "required": ["job_id"],
        },
        permission_class="read_only",
        fallback=(
            "I couldn't load that job's details right now. You can view it directly at "
            "/jobs/{job_id}."
        ),
        audit_event_type="TOOL_GET_JOB_DETAIL",
    ),
    "get_my_registered_events": ToolSpec(
        name="get_my_registered_events",
        description=(
            "Get the events the student has registered for. Returns upcoming registrations with "
            "event title, date, type, format, venue, and registration status (confirmed, "
            "waitlisted). Use this when the student asks 'what events have I signed up for', 'show "
            "my event registrations', 'am I going to any career fairs', or wants to check if they "
            "are on a waitlist. Only available to student users."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback="I couldn't load your registered events. Check /events for your upcoming events.",
        audit_event_type="TOOL_GET_MY_REGISTERED_EVENTS",
    ),
    "get_company_detail": ToolSpec(
        name="get_company_detail",
        description=(
            "Get the public profile for a specific company: industry, size, tagline, open job "
            "count, and their latest rating. Use this when the student asks 'tell me about "
            "[company]', 'what do people think of [company]', 'how big is [company]', or asks for "
            "details about a specific employer they found in a job listing. Pass the company slug "
            "(e.g. 'acme-corp') or the company name from a prior search result."
        ),
        parameters={
            "type": "object",
            "properties": {
                "slug": {
                    "type": "string",
                    "description": (
                        "Company slug (URL-safe name) from a search result or job listing"
                    ),
                },
            },
            "required": ["slug"],
        },
        permission_class="read_only",
        fallback=(
            "I couldn't load that company's profile. You can view it directly on the Companies "
            "page."
        ),
        audit_event_type="TOOL_GET_COMPANY_DETAIL",
    ),
    "search_events": ToolSpec(
        name="search_events",
        description=(
            "Search the public events board by keyword or event type. Returns matching events with "
            "date, type, format, and registration status. Use this when the student asks 'are "
            "there any AI workshops?', 'find networking events this month', 'show me career "
            "fairs', or searches for events by topic. Prefer this over get_upcoming_events when "
            "there is a search keyword."
        ),
        parameters={
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Search keyword, e.g. 'AI', 'data science', 'networking'",
                },
                "event_type": {
                    "type": "string",
                    "enum": ["career_fair", "workshop", "info_session", "networking", "webinar"],
                    "description": "Filter by event type",
                },
            },
            "required": [],
        },
        permission_class="read_only",
        fallback="I couldn't search events right now. Browse /events to find upcoming activities.",
        audit_event_type="TOOL_SEARCH_EVENTS",
    ),
    "get_partner_jobs": ToolSpec(
        name="get_partner_jobs",
        description=(
            "Get the partner organisation's own job postings with application counts. Use this "
            "when the partner or recruiter asks about their job listings, which jobs are active, "
            "how many applicants each role has, or which jobs are pending moderation. Only "
            "available to partner users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["draft", "pending", "active", "closed"],
                    "description": "Filter by job status",
                },
            },
            "required": [],
        },
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback="I couldn't load your jobs right now. Check /partner/jobs for your listings.",
        audit_event_type="TOOL_GET_PARTNER_JOBS",
    ),
    "get_partner_pipeline_summary": ToolSpec(
        name="get_partner_pipeline_summary",
        description=(
            "Get a summary of the partner's recruitment pipeline — per-job counts of active, "
            "rejected, and withdrawn candidates. Use this when the partner asks about their "
            "candidate pipeline, how many applicants they have across all roles, or which jobs "
            "have the most candidates. Only available to partner users."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback=(
            "I couldn't load your pipeline summary right now. Check /partner/pipeline for details."
        ),
        audit_event_type="TOOL_GET_PARTNER_PIPELINE_SUMMARY",
    ),
    "get_skill_gap": ToolSpec(
        name="get_skill_gap",
        description=(
            "Analyse the gap between the student's current CV skills and the required skills for a "
            "target job. Returns which required skills are present, which are missing, and a fit "
            "score. Use this when the student asks 'am I a good fit for this job?', 'what skills "
            "do I need for [role]?', 'how does my CV compare to this job?', or 'what should I "
            "learn to qualify for this position?'. Requires a job_id from a prior search_jobs or "
            "get_job_detail result. Only for student users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job UUID from a prior search_jobs or get_job_detail result",
                },
                "cv_id": {
                    "type": "string",
                    "description": (
                        "Optional CV UUID. If omitted, the student's primary active CV is used."
                    ),
                },
            },
            "required": ["job_id"],
        },
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback=(
            "I couldn't run the skill gap analysis right now. Check the job page at /jobs/{job_id} "
            "for requirements."
        ),
        audit_event_type="TOOL_GET_SKILL_GAP",
        timeout_seconds=20,
    ),
    "recommend_jobs": ToolSpec(
        name="recommend_jobs",
        description=(
            "Get personalised job recommendations for the student based on their CV skills, active "
            "applications, and saved preferences. Returns up to 5 recommended jobs with match "
            "score and reason. Use this when the student asks 'what jobs should I apply for?', "
            "'recommend jobs for me', 'jobs that match my profile', 'what do you suggest?', or "
            "'jobs similar to what I've saved'. Only for student users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of recommendations (default 5, max 10)",
                },
            },
            "required": [],
        },
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback=(
            "I couldn't generate recommendations right now. Browse /jobs to discover "
            "opportunities."
        ),
        audit_event_type="TOOL_RECOMMEND_JOBS",
        timeout_seconds=20,
    ),
    "get_career_advice": ToolSpec(
        name="get_career_advice",
        description=(
            "Get structured career advice for a specific occupation or career transition goal. "
            "Returns a brief career overview, typical salary range in Vietnam, key skills to "
            "develop, suggested certifications, and growth path. Use this when the student asks "
            "'what does a data scientist do?', 'how do I become a product manager?', 'what career "
            "paths are there in finance?', 'what skills does a software engineer need?', 'how do I "
            "switch from X to Y?', or 'what's the career path for [role]?'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": (
                        "Target job title or career path, e.g. 'data scientist', 'product manager'"
                    ),
                },
                "current_role": {
                    "type": "string",
                    "description": (
                        "Optional: the student's current or most recent role to personalise "
                        "transition advice"
                    ),
                },
            },
            "required": ["role"],
        },
        permission_class="read_only",
        fallback=(
            "I couldn't retrieve career advice right now. Try searching for the role to see active "
            "job postings."
        ),
        audit_event_type="TOOL_GET_CAREER_ADVICE",
    ),
    "get_salary_benchmark": ToolSpec(
        name="get_salary_benchmark",
        description=(
            "Look up typical salary ranges for a job title in Vietnam (and optionally a specific "
            "city). Returns min/median/max monthly salary in VND and USD, years-of-experience "
            "tiers, and data source context. Use this when the student asks 'how much does a "
            "[role] earn?', 'what is the salary for [title]?', 'is this salary offer fair?', 'what "
            "should I expect to earn?', or 'salary range in Hanoi for X'. Salary data is "
            "approximate market data; never guarantee specific employer offers."
        ),
        parameters={
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": (
                        "Job title to benchmark, e.g. 'software engineer', 'marketing manager'"
                    ),
                },
                "city": {
                    "type": "string",
                    "description": (
                        "Optional city context: 'hanoi', 'ho chi minh city', or 'remote'"
                    ),
                },
                "experience_years": {
                    "type": "integer",
                    "description": "Optional: years of experience to narrow the salary tier",
                },
            },
            "required": ["role"],
        },
        permission_class="read_only",
        fallback=(
            "I couldn't retrieve salary data right now. Check the job listings for disclosed "
            "salary ranges."
        ),
        audit_event_type="TOOL_GET_SALARY_BENCHMARK",
    ),
    "start_interview_sim": ToolSpec(
        name="start_interview_sim",
        description=(
            "Start an AI-powered mock interview for a specific job or role. Returns an opening "
            "interview question personalised to the role and the student's CV background. Use this "
            "when the student asks 'help me practice for an interview', 'what questions will they "
            "ask?', 'mock interview', 'interview practice for [role]', or 'prepare for [company] "
            "interview'. Requires job_id OR role."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": (
                        "Optional job posting ID to tailor questions to the specific role"
                    ),
                },
                "role": {
                    "type": "string",
                    "description": (
                        "Role title if no specific job ID, e.g. 'software engineer', 'data "
                        "analyst'"
                    ),
                },
                "round": {
                    "type": "string",
                    "enum": ["screening", "technical", "behavioral", "final"],
                    "description": "Interview round type (default: screening)",
                },
            },
            "required": [],
        },
        permission_class="read_only",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        fallback=(
            "I couldn't start the interview simulation right now. Try reviewing common interview "
            "questions at /resources/interview-prep."
        ),
        audit_event_type="TOOL_START_INTERVIEW_SIM",
        timeout_seconds=20,
    ),
    "save_job": ToolSpec(
        name="save_job",
        description=(
            "Save a job posting to the student's saved jobs list. Use this when the student says "
            "'save this job', 'bookmark job', 'add to saved', or 'I want to apply to this later'. "
            "Requires the student to confirm before executing."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job posting ID to save",
                },
            },
            "required": ["job_id"],
        },
        permission_class="confirmation_required",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        side_effects=["INSERT saved_jobs row"],
        confirmation_copy=ConfirmationCopy(
            title_key="confirm.card.save_job.title",
            body_key="confirm.card.save_job.body",
            cta_confirm_key="confirm.card.save_job.cta_confirm",
        ),
        fallback=(
            "I couldn't save the job right now. Visit the job page and use the heart button to "
            "save it."
        ),
        audit_event_type="TOOL_SAVE_JOB",
    ),
    "apply_job": ToolSpec(
        name="apply_job",
        description=(
            "Submit a job application on behalf of the student using their active CV. Use when the "
            "student says 'apply to this job', 'submit my application', or 'apply now'. Requires "
            "the student to confirm before executing. Do NOT call this tool if the student has not "
            "yet selected or mentioned a specific job."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job posting ID to apply to",
                },
                "cv_id": {
                    "type": "string",
                    "description": (
                        "Optional: the CV ID to use. If omitted, the student's active CV is used."
                    ),
                },
                "cover_letter": {
                    "type": "string",
                    "description": (
                        "Optional cover letter body to attach to the application (e.g. a draft "
                        "produced by draft_and_attach_cover_letter). If omitted, no cover letter "
                        "is attached."
                    ),
                },
            },
            "required": ["job_id"],
        },
        permission_class="confirmation_required",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        side_effects=["INSERT job_applications row", "notification to partner"],
        confirmation_copy=ConfirmationCopy(
            title_key="confirm.card.apply_job.title",
            body_key="confirm.card.apply_job.body",
            cta_confirm_key="confirm.card.apply_job.cta_confirm",
        ),
        fallback=(
            "Tôi không thể nộp đơn lúc này. Bạn có thể truy cập trang việc làm và nhấn 'Ứng tuyển' "
            "trực tiếp."
        ),
        audit_event_type="TOOL_APPLY_JOB",
    ),
    "tailor_cv_to_job": ToolSpec(
        name="tailor_cv_to_job",
        description=(
            "Produce a CV Studio improvement DRAFT that tailors one of the student's own "
            "template CVs to a specific job's requirements. Use this when the student says "
            "'tailor my CV for this job', 'optimise my CV for [role]', or 'help me improve my CV "
            "for this position'. Requires a job_id (from a prior search_jobs/get_job_detail). "
            "Produces a PENDING, structured diff (never auto-applied) that the student reviews and "
            "accepts in CV Studio; it never invents experience the CV does not support. Requires "
            "the student to confirm before drafting. Only for student users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job UUID to tailor the CV toward",
                },
                "cv_id": {
                    "type": "string",
                    "description": (
                        "Optional CV UUID. If omitted, the best-matching template CV is used."
                    ),
                },
            },
            "required": ["job_id"],
        },
        permission_class="confirmation_required",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        side_effects=[
            "INSERT cv_ai_suggestions row (pending diff)",
            "debit AI energy (cv_edit_command)",
        ],
        confirmation_copy=ConfirmationCopy(
            title_key="confirm.card.tailor_cv_to_job.title",
            body_key="confirm.card.tailor_cv_to_job.body",
            cta_confirm_key="confirm.card.tailor_cv_to_job.cta_confirm",
        ),
        fallback=(
            "I couldn't draft CV tailoring right now. Open the CV in CV Studio and use the AI "
            "improve tools, or compare your CV to the job with a skill-gap check first."
        ),
        audit_event_type="TOOL_TAILOR_CV_TO_JOB",
        timeout_seconds=25,
    ),
    "draft_and_attach_cover_letter": ToolSpec(
        name="draft_and_attach_cover_letter",
        description=(
            "Draft a personalised cover letter for a specific job and hand it back ready to attach "
            "to the student's application for that job. Use this when the student says 'write a "
            "cover letter for this job', 'draft a cover letter', or 'help me apply with a cover "
            "letter'. Requires a job_id. The draft grounds only on the job and the student's own "
            "profile/CV and never invents qualifications; it is returned for the "
            "confirmation-gated apply flow and is never sent to the employer until the student "
            "applies. Requires the "
            "student to confirm before drafting. Only for student users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job UUID to draft a cover letter for",
                },
                "cv_id": {
                    "type": "string",
                    "description": (
                        "Optional CV UUID to use when the student proceeds to apply with the draft."
                    ),
                },
                "note": {
                    "type": "string",
                    "description": (
                        "Optional short note from the student to steer the draft "
                        "(e.g. 'emphasise my internship')."
                    ),
                },
            },
            "required": ["job_id"],
        },
        permission_class="confirmation_required",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        side_effects=[
            "generate cover letter draft",
            "debit AI energy (cover_letter)",
            "return draft for the apply flow (no employer send)",
        ],
        confirmation_copy=ConfirmationCopy(
            title_key="confirm.card.cover_letter.title",
            body_key="confirm.card.cover_letter.body",
            cta_confirm_key="confirm.card.cover_letter.cta_confirm",
        ),
        fallback=(
            "I couldn't draft a cover letter right now. You can still apply and write a short "
            "cover letter yourself on the application page."
        ),
        audit_event_type="TOOL_DRAFT_COVER_LETTER",
        timeout_seconds=25,
    ),
    "set_job_alert": ToolSpec(
        name="set_job_alert",
        description=(
            "Create a saved job alert subscription from the student's current search criteria so "
            "they get notified about matching new jobs. Use this when the student says 'notify me "
            "about jobs like this', 'create a job alert for [keywords]', or 'save this search'. "
            "Requires the student to confirm before creating. Only for student users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "Search keywords for the alert, e.g. 'data analyst'",
                },
                "employment_type": {
                    "type": "string",
                    "description": (
                        "Optional employment type filter, e.g. 'full_time', 'internship'"
                    ),
                },
                "location_type": {
                    "type": "string",
                    "description": "Optional work mode filter, e.g. 'remote', 'onsite', 'hybrid'",
                },
                "province_code": {
                    "type": "string",
                    "description": "Optional province code, e.g. 'HN' for Hanoi",
                },
                "name": {
                    "type": "string",
                    "description": "Optional display name for the alert. Defaults to the keywords.",
                },
            },
            "required": [],
        },
        permission_class="confirmation_required",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        side_effects=["INSERT job_alerts row"],
        confirmation_copy=ConfirmationCopy(
            title_key="confirm.card.set_job_alert.title",
            body_key="confirm.card.set_job_alert.body",
            cta_confirm_key="confirm.card.set_job_alert.cta_confirm",
        ),
        fallback=(
            "I couldn't create the job alert right now. You can manage alerts at /student/alerts."
        ),
        audit_event_type="TOOL_SET_JOB_ALERT",
    ),
    "register_for_event": ToolSpec(
        name="register_for_event",
        description=(
            "Register the student for a specific career event, workshop, or fair. Use this when "
            "the student says 'register me for this event', 'sign me up', or 'RSVP to [event]'. "
            "Requires an event_id (from a prior search_events/get_upcoming_events). A full event "
            "adds the student to the waitlist. Requires the student to confirm before registering. "
            "Only for student users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "Event UUID to register for",
                },
            },
            "required": ["event_id"],
        },
        permission_class="confirmation_required",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        side_effects=[
            "INSERT event_registrations row (confirmed or waitlisted)",
            "notification to student",
        ],
        confirmation_copy=ConfirmationCopy(
            title_key="confirm.card.register_for_event.title",
            body_key="confirm.card.register_for_event.body",
            cta_confirm_key="confirm.card.register_for_event.cta_confirm",
        ),
        fallback=(
            "I couldn't register you for the event right now. Open the event page at "
            "/events and use the Register button."
        ),
        audit_event_type="TOOL_REGISTER_FOR_EVENT",
    ),
    "search_partner_candidates": ToolSpec(
        name="search_partner_candidates",
        description=(
            "Search/shortlist the partner's own applicants for one of their jobs, "
            "optionally filtered by pipeline stage or a keyword. Use this when the "
            "recruiter asks to find candidates for a role, filter by stage (e.g. "
            "'interview'), or search their applicant list. Requires job_id from a "
            "prior get_partner_jobs result. Anonymous-apply candidates are shown "
            "with a generic label, never their real identity, until reveal is "
            "accepted in the platform UI. Only available to partner users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job UUID owned by the partner's org"},
                "stage": {"type": "string", "description": "Optional stage/status keyword filter"},
                "q": {"type": "string", "description": "Optional keyword to match candidate label"},
            },
            "required": ["job_id"],
        },
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback=(
            "I couldn't search candidates right now. Check /partner/pipeline for your applicants."
        ),
        audit_event_type="TOOL_SEARCH_PARTNER_CANDIDATES",
    ),
    "get_candidate_detail": ToolSpec(
        name="get_candidate_detail",
        description=(
            "Get a single applicant's current pipeline stage, CV snapshot "
            "availability, and status. Use this when the recruiter asks about a "
            "specific candidate's progress or wants to check their stage before "
            "an interview. Requires application_id from a prior "
            "search_partner_candidates result. Never returns raw CV bytes — only "
            "a snapshot-availability flag and the platform link. Only available "
            "to partner users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "string",
                    "description": "Application UUID from a prior search_partner_candidates result",
                },
            },
            "required": ["application_id"],
        },
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback=(
            "I couldn't load that candidate's details right now. Check the pipeline board "
            "at /partner/pipeline."
        ),
        audit_event_type="TOOL_GET_CANDIDATE_DETAIL",
    ),
    "draft_job_description": ToolSpec(
        name="draft_job_description",
        description=(
            "Generate a DRAFT job description for a NEW job posting from a title and "
            "optional details (skills, responsibilities, benefits). Use this when the "
            "recruiter asks to write or draft a job posting from scratch. The result "
            "is advisory text only — nothing is saved. The recruiter must review, "
            "edit, and create the job themselves. Only available to partner users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Job title"},
                "employment_type": {"type": "string"},
                "experience_level": {"type": "string"},
                "location": {"type": "string"},
                "required_skills": {"type": "string"},
                "preferred_skills": {"type": "string"},
                "responsibilities": {"type": "string"},
                "benefits": {"type": "string"},
                "partner_instruction": {
                    "type": "string",
                    "description": "Optional free-text guidance from the recruiter",
                },
            },
            "required": ["title"],
        },
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback=(
            "I couldn't draft a job description right now. Try the JD writer at "
            "/partner/jobs/new."
        ),
        audit_event_type="TOOL_DRAFT_JOB_DESCRIPTION",
        timeout_seconds=20,
    ),
    "rewrite_job_description": ToolSpec(
        name="rewrite_job_description",
        description=(
            "Generate a DRAFT rewrite of an EXISTING job posting the partner owns. "
            "Use this when the recruiter asks to improve, rewrite, or refresh a job "
            "description they already published. Requires job_id from a prior "
            "get_partner_jobs result. The result is advisory text only — the job "
            "record is never modified by this tool; the recruiter must review and "
            "save changes themselves. Only available to partner users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job UUID owned by the partner's org"},
                "partner_instruction": {
                    "type": "string",
                    "description": "Optional free-text guidance, e.g. 'make it shorter'",
                },
            },
            "required": ["job_id"],
        },
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback=(
            "I couldn't rewrite that job description right now. Try editing it directly at "
            "/partner/jobs/{job_id}."
        ),
        audit_event_type="TOOL_REWRITE_JOB_DESCRIPTION",
        timeout_seconds=20,
    ),
    "check_jd_bias": ToolSpec(
        name="check_jd_bias",
        description=(
            "Scan job description text for biased or discriminatory phrasing (age, "
            "gender, disability, marital status, appearance). Use this when the "
            "recruiter asks to check a JD draft for bias or compliance before "
            "publishing. Deterministic and offline — always available. Only "
            "available to partner users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The job description text to check"},
            },
            "required": ["text"],
        },
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback="I couldn't run the bias check right now. Please review the text manually.",
        audit_event_type="TOOL_CHECK_JD_BIAS",
    ),
    "suggest_scorecard": ToolSpec(
        name="suggest_scorecard",
        description=(
            "Suggest DRAFT scorecard scores (technical, communication, culture fit, "
            "motivation) from free-text interviewer notes for one application. Use "
            "this when the recruiter asks for help scoring an interview from their "
            "notes. Advisory only — never submitted automatically; the interviewer "
            "must review and submit the real scorecard. Confidence is high/medium/low "
            "only, never a raw score. Only available to partner users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "application_id": {"type": "string", "description": "Application UUID"},
                "notes": {"type": "string", "description": "Free-text interviewer notes"},
                "job_title": {"type": "string"},
                "interview_stage": {"type": "string"},
            },
            "required": ["application_id", "notes"],
        },
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback=(
            "I couldn't generate a scorecard suggestion right now. Fill in the scorecard "
            "manually from the application detail page."
        ),
        audit_event_type="TOOL_SUGGEST_SCORECARD",
        timeout_seconds=20,
    ),
    "generate_screening_brief": ToolSpec(
        name="generate_screening_brief",
        description=(
            "Generate a 3-4 bullet screening brief comparing a candidate's CV to the "
            "job requirements — a relevant strength, another strength, a gap if any, "
            "and an overall suitability signal. Use this when the recruiter asks for "
            "a quick read on a candidate before reviewing the full application. "
            "Privacy-safe: no candidate name or contact info is used. Requires "
            "application_id. Only available to partner users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "application_id": {"type": "string", "description": "Application UUID"},
            },
            "required": ["application_id"],
        },
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback=(
            "I couldn't generate a screening brief right now. Review the CV directly on "
            "the application page."
        ),
        audit_event_type="TOOL_GENERATE_SCREENING_BRIEF",
        timeout_seconds=20,
    ),
    "get_upcoming_partner_events": ToolSpec(
        name="get_upcoming_partner_events",
        description=(
            "Get the partner organisation's own upcoming hosted events (career fairs, "
            "workshops, info sessions). Use this when the recruiter asks about their "
            "hosted events, upcoming activities, or registration counts. Only "
            "available to partner users."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        fallback="I couldn't load your events right now. Check /partner/events for your listings.",
        audit_event_type="TOOL_GET_UPCOMING_PARTNER_EVENTS",
    ),
    "move_candidate_stage": ToolSpec(
        name="move_candidate_stage",
        description=(
            "Advance a candidate's application to the NEXT pipeline stage. Use this "
            "ONLY when the recruiter explicitly asks to move/advance a specific "
            "candidate, e.g. 'move this candidate to the next stage'. Requires the "
            "recruiter to confirm before executing. Requires application_id from a "
            "prior search_partner_candidates or get_candidate_detail result. Only "
            "available to partner users."
        ),
        parameters={
            "type": "object",
            "properties": {
                "application_id": {"type": "string", "description": "Application UUID to advance"},
            },
            "required": ["application_id"],
        },
        permission_class="confirmation_required",
        persona=[PARTNER_USER],
        required_permissions=["authenticated", "role:partner_user"],
        side_effects=[
            "UPDATE candidate_stages (close current, open next)",
            "UPDATE applications.version",
            "notification to student (if next stage is candidate-visible)",
        ],
        confirmation_copy=ConfirmationCopy(
            title_key="confirm.card.move_candidate_stage.title",
            body_key="confirm.card.move_candidate_stage.body",
            cta_confirm_key="confirm.card.move_candidate_stage.cta_confirm",
        ),
        fallback=(
            "I couldn't move that candidate right now. Use the pipeline board at "
            "/partner/pipeline to advance them manually."
        ),
        audit_event_type="TOOL_MOVE_CANDIDATE_STAGE",
    ),
    "knowledge_base_query": ToolSpec(
        name="knowledge_base_query",
        description=(
            "Search the VinUni Career Platform knowledge base to answer questions about: platform "
            "policies, application processes, employer information, internship guidelines, or any "
            "documents uploaded to the knowledge base. Use when the student asks 'how does X "
            "work', 'what is the policy for Y', or 'tell me about Z company'. Do NOT use for "
            "real-time job search — use search_jobs instead."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The question or topic to search the knowledge base for",
                },
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "answer": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "object"}},
            },
        },
        permission_class="read_only",
        fallback=(
            "Tôi không tìm thấy thông tin về chủ đề này trong cơ sở kiến thức. Vui lòng liên hệ "
            "phòng hỗ trợ sinh viên để được giải đáp."
        ),
        audit_event_type="TOOL_KB_QUERY",
        timeout_seconds=20,
    ),
}
