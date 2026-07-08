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
    """User-facing confirmation card copy for a mutating tool (§4.3)."""

    title: str
    body: str
    cta_confirm: str
    cta_cancel: str = "Huỷ"


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
            title="Lưu tin tuyển dụng này?",
            body="Việc làm sẽ được thêm vào danh sách đã lưu của bạn.",
            cta_confirm="Lưu",
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
            },
            "required": ["job_id"],
        },
        permission_class="confirmation_required",
        persona=[STUDENT],
        required_permissions=["authenticated", "role:student"],
        side_effects=["INSERT job_applications row", "notification to partner"],
        confirmation_copy=ConfirmationCopy(
            title="Nộp đơn ứng tuyển?",
            body=(
                "Bạn sẽ ứng tuyển vào vị trí này bằng CV đã chọn "
                "(hoặc CV chính nếu không chỉ định)."
            ),
            cta_confirm="Xác nhận nộp đơn",
        ),
        fallback=(
            "Tôi không thể nộp đơn lúc này. Bạn có thể truy cập trang việc làm và nhấn 'Ứng tuyển' "
            "trực tiếp."
        ),
        audit_event_type="TOOL_APPLY_JOB",
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
            title="Chuyển ứng viên sang vòng tiếp theo?",
            body=(
                "Ứng viên sẽ được chuyển sang vòng tuyển dụng tiếp theo trong quy trình. "
                "Hành động này sẽ được ghi nhận và có thể thông báo cho ứng viên."
            ),
            cta_confirm="Xác nhận chuyển vòng",
        ),
        fallback=(
            "I couldn't move that candidate right now. Use the pipeline board at "
            "/partner/pipeline to advance them manually."
        ),
        audit_event_type="TOOL_MOVE_CANDIDATE_STAGE",
    ),
    # ----------------------------------------------------------------------- #
    # University staff — operations copilot (persona=[UNIVERSITY_STAFF]).      #
    # Each tool declares precise catalog grants; the central dispatch RBAC     #
    # gate (dispatch.authorize_tool) enforces them, and each underlying        #
    # service does its own authoritative org-scoped + org_type=university      #
    # check. Reads return privacy-safe aggregates; the two writes are          #
    # confirmation-gated, audited, and advisory (human final say).             #
    # ----------------------------------------------------------------------- #
    "get_university_dashboard_summary": ToolSpec(
        name="get_university_dashboard_summary",
        description=(
            "Get the university operations command-center rollup: number of jobs pending "
            "moderation, partner registrations pending approval, active partners, active "
            "jobs, and the recommended next actions. Use this when staff ask 'what needs my "
            "attention', 'operations overview', 'how many jobs are pending', or open their "
            "day. Only available to university staff."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "jobs:moderate"],
        fallback="I couldn't load the operations overview right now. Check /university.",
        audit_event_type="TOOL_GET_UNIVERSITY_DASHBOARD_SUMMARY",
    ),
    "get_moderation_queue": ToolSpec(
        name="get_moderation_queue",
        description=(
            "Get the jobs awaiting university moderation, oldest first, with each item's age "
            "in hours and whether it is overdue against its SLA. Use this when staff ask to "
            "review the moderation queue, see what is pending or overdue, or triage jobs by "
            "age. Advisory only — approving or sending a job back is a human decision. Only "
            "available to university staff."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": (
                        "Optional job status filter (default pending_review), e.g. "
                        "'pending_review', 'rejected'."
                    ),
                },
            },
            "required": [],
        },
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "jobs:moderate"],
        fallback=(
            "I couldn't load the moderation queue right now. Check "
            "/university/moderation/jobs."
        ),
        audit_event_type="TOOL_GET_MODERATION_QUEUE",
    ),
    "get_ai_review_queue": ToolSpec(
        name="get_ai_review_queue",
        description=(
            "Get the AI/rule-FLAGGED jobs and events awaiting a human moderator's final "
            "decision (the AI human-review queue), oldest flag first, each with a plain-language "
            "flag reason, its age in hours, and whether it is overdue against the AI-review SLA. "
            "Use this when staff ask what has been flagged, what needs a human decision, or which "
            "flagged items are overdue. Advisory only — AI flags are not decisions; upholding "
            "(rejecting) or dismissing a flag is a human call. Only available to university staff."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "jobs:moderate"],
        fallback=(
            "I couldn't load the AI review queue right now. Check "
            "/university/moderation."
        ),
        audit_event_type="TOOL_GET_AI_REVIEW_QUEUE",
    ),
    "get_pending_partner_registrations": ToolSpec(
        name="get_pending_partner_registrations",
        description=(
            "Get partner organisations awaiting university approval (the partner governance "
            "queue), with company name, industry, size, and submission time. Use this when "
            "staff ask about pending partners, new partner requests, or partners to review. "
            "Contact person details are never shown in chat. Only available to university "
            "staff."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "partners:read"],
        fallback=(
            "I couldn't load pending partner registrations right now. Check "
            "/university/moderation/partners."
        ),
        audit_event_type="TOOL_GET_PENDING_PARTNER_REGISTRATIONS",
    ),
    "get_partner_overview": ToolSpec(
        name="get_partner_overview",
        description=(
            "Get a partner governance rollup: number of active partners and a count of "
            "partner registrations grouped by status. Use this when staff ask for a partner "
            "overview, how many partners are active, or the state of partner onboarding. "
            "Only available to university staff."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "partners:read"],
        fallback="I couldn't load the partner overview right now. Check /university/partners.",
        audit_event_type="TOOL_GET_PARTNER_OVERVIEW",
    ),
    "get_at_risk_students": ToolSpec(
        name="get_at_risk_students",
        description=(
            "Get a privacy-safe summary of career-services at-risk flags: counts by severity "
            "and status plus a short recent list (reason, severity, status only — never "
            "student names, emails, or private detail). Use this when staff ask about at-risk "
            "students, students needing support, or open risk flags. Only available to "
            "university staff with career-services access."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=[
            "authenticated",
            "role:university_staff",
            "career_services_at_risk:read",
        ],
        fallback=(
            "I couldn't load at-risk students right now. Check "
            "/university/students/at-risk."
        ),
        audit_event_type="TOOL_GET_AT_RISK_STUDENTS",
    ),
    "get_cohort_summary": ToolSpec(
        name="get_cohort_summary",
        description=(
            "Get the career-services cohorts the caller's organisation owns, with name, "
            "description, and status. Use this when staff ask about cohorts, student groups, "
            "or which cohorts are active. Only available to university staff with "
            "career-services access."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=[
            "authenticated",
            "role:university_staff",
            "career_services_cohorts:read",
        ],
        fallback="I couldn't load cohorts right now. Check /university/students/cohorts.",
        audit_event_type="TOOL_GET_COHORT_SUMMARY",
    ),
    "get_career_services_report": ToolSpec(
        name="get_career_services_report",
        description=(
            "Get the counselor-workspace aggregate report: active cohorts, open at-risk "
            "flags, open CV reviews, and distributions of at-risk severity and appointments "
            "by status. Use this when staff ask for a career-services report, workspace "
            "summary, or how counseling operations are tracking. Only available to university "
            "staff with career-services reporting access."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=[
            "authenticated",
            "role:university_staff",
            "career_services_reporting:read",
        ],
        fallback=(
            "I couldn't load the career-services report right now. Check /university/students."
        ),
        audit_event_type="TOOL_GET_CAREER_SERVICES_REPORT",
    ),
    "get_placement_outcomes_summary": ToolSpec(
        name="get_placement_outcomes_summary",
        description=(
            "Get the university career-outcomes KPI roll-up: total recorded outcomes, mix by "
            "trust level, top employers, and a few recent placements (position, employer, "
            "outcome — no student PII). Use this when staff ask about placement outcomes, "
            "employment results, top hiring employers, or graduate outcomes. Only available "
            "to university staff."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "jobs:moderate"],
        fallback=(
            "I couldn't load placement outcomes right now. Check "
            "/university/analytics/outcomes."
        ),
        audit_event_type="TOOL_GET_PLACEMENT_OUTCOMES_SUMMARY",
    ),
    "start_operations_analysis": ToolSpec(
        name="start_operations_analysis",
        description=(
            "Kick off a deeper, multi-step operations analysis of ONE partner "
            "employer's hiring quality. A set of specialist read-passes look at the "
            "partner's job-posting hygiene, application pipeline, recorded graduate "
            "outcomes, and moderation friction, then compose one privacy-safe "
            "report with findings and advisory recommendations. Use this when staff "
            "ask for a thorough review or 'deep dive' on a specific partner (e.g. "
            "'analyse this employer's hiring quality', 'phân tích chất lượng tuyển "
            "dụng của đối tác này'). It runs in the background — this call returns a "
            "run id; then call get_operations_analysis with that id to read the "
            "report. Requires the partner organisation's id. Read-only and "
            "advisory. Only available to university staff with partner access."
        ),
        parameters={
            "type": "object",
            "properties": {
                "target_org_id": {
                    "type": "string",
                    "description": "Partner organisation UUID to analyse",
                },
                "target_type": {
                    "type": "string",
                    "description": (
                        "Analysis target (default 'partner_hiring_quality')"
                    ),
                },
            },
            "required": ["target_org_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "run_id": {"type": "string"},
                "status": {"type": "string"},
                "total_subtasks": {"type": "integer"},
            },
        },
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "partners:read"],
        fallback=(
            "I couldn't start the partner analysis right now. Check the partner's "
            "profile under /university/partners."
        ),
        audit_event_type="TOOL_START_OPERATIONS_ANALYSIS",
        timeout_seconds=20,
    ),
    "get_operations_analysis": ToolSpec(
        name="get_operations_analysis",
        description=(
            "Read the status and (once finished) the report of a partner "
            "operations analysis you previously started with "
            "start_operations_analysis. Returns overall status, how many of the "
            "analysis passes are done, and — when complete — a structured report "
            "with a summary, findings by area, advisory recommendations, and "
            "caveats. Requires the run_id returned by start_operations_analysis. "
            "Only available to university staff."
        ),
        parameters={
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "string",
                    "description": "Run UUID returned by start_operations_analysis",
                },
            },
            "required": ["run_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "status": {"type": "string"},
                "summary": {"type": "object"},
            },
        },
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "partners:read"],
        fallback=(
            "I couldn't load that analysis right now. You can start a new one or "
            "check /university/partners."
        ),
        audit_event_type="TOOL_GET_OPERATIONS_ANALYSIS",
    ),
    "search_university_knowledge": ToolSpec(
        name="search_university_knowledge",
        description=(
            "Search the knowledge bases the staff member is authorised to read to answer "
            "questions about university policies, processes, guidelines, or uploaded "
            "documents. Use for 'what is the policy for X', 'how does process Y work', or "
            "internal reference lookups. Scoped to the caller's readable knowledge bases — "
            "never another organisation's. Only available to university staff."
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
                "found": {"type": "boolean"},
                "context": {"type": "string"},
            },
        },
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff"],
        fallback=(
            "I couldn't find that in the knowledge base. Try the university operations docs "
            "or contact an administrator."
        ),
        audit_event_type="TOOL_SEARCH_UNIVERSITY_KNOWLEDGE",
        timeout_seconds=20,
    ),
    "analyze_attachment": ToolSpec(
        name="analyze_attachment",
        description=(
            "Read and analyse a file or image the staff member attached to THIS chat "
            "session — transcribe/summarise it and, when it contains data, draw tables and "
            "charts (columns/bars, lines, or a pie) and surface factual insights (totals, "
            "min/max/average). Use this when staff ask you to read, analyse, summarise, or "
            "visualise an attachment they uploaded (e.g. 'phân tích file này', 'vẽ bảng và "
            "biểu đồ cột từ dữ liệu này', 'đọc ảnh này', 'summarise this document', 'chart "
            "these numbers'). Requires attachment_id — the id returned when the staffer "
            "uploaded the attachment to this session. Only reads the staffer's OWN "
            "attachment; never fabricates content for a blank or unreadable file. Only "
            "available to university staff."
        ),
        parameters={
            "type": "object",
            "properties": {
                "attachment_id": {
                    "type": "string",
                    "description": (
                        "UUID of the attachment the staff member uploaded to this chat session"
                    ),
                },
            },
            "required": ["attachment_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "status": {"type": "string"},
                "kind": {"type": "string"},
                "analyzed": {"type": "boolean"},
                "summary": {"type": "string"},
                "insights": {"type": "array", "items": {"type": "string"}},
                "tables": {"type": "array", "items": {"type": "object"}},
                "charts": {"type": "array", "items": {"type": "object"}},
            },
        },
        permission_class="read_only",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff"],
        fallback=(
            "I couldn't analyse that attachment right now. Make sure you uploaded a readable "
            "PDF, image, DOCX, TXT, or CSV to this chat, then try again."
        ),
        audit_event_type="TOOL_ANALYZE_ATTACHMENT",
        timeout_seconds=30,
    ),
    "approve_job_moderation": ToolSpec(
        name="approve_job_moderation",
        description=(
            "Approve a pending job and publish it. Use ONLY when the staff member explicitly "
            "asks to approve a specific job from the moderation queue. Requires the staff "
            "member's confirmation before executing; the posting partner is notified and the "
            "decision is audited. Requires job_id from a prior get_moderation_queue result. "
            "Advisory — the human makes the decision. Only available to university staff."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job UUID to approve"},
                "version": {
                    "type": "integer",
                    "description": "Optional expected job version for optimistic concurrency",
                },
            },
            "required": ["job_id"],
        },
        permission_class="confirmation_required",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "jobs:moderate"],
        side_effects=[
            "UPDATE jobs (pending_review -> active, publish)",
            "audit job.approved",
            "notification to posting partner",
        ],
        confirmation_copy=ConfirmationCopy(
            title="Duyệt và đăng tin tuyển dụng này?",
            body=(
                "Tin tuyển dụng sẽ được duyệt và đăng công khai. Đối tác đăng tin sẽ được "
                "thông báo và hành động này được ghi nhật ký."
            ),
            cta_confirm="Xác nhận duyệt",
        ),
        fallback=(
            "I couldn't approve that job right now. Use /university/moderation/jobs to review "
            "and approve it."
        ),
        audit_event_type="TOOL_APPROVE_JOB_MODERATION",
    ),
    "request_job_changes": ToolSpec(
        name="request_job_changes",
        description=(
            "Send a pending job back to the posting partner with a required reason so they "
            "can revise and resubmit. Use ONLY when the staff member explicitly asks to "
            "reject or request changes on a specific job, and provide a clear reason. "
            "Requires confirmation; the partner is notified with the reason and the decision "
            "is audited. Requires job_id from a prior get_moderation_queue result. Advisory — "
            "the human makes the decision. Only available to university staff."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job UUID to send back"},
                "reason": {
                    "type": "string",
                    "description": "Required explanation of the changes the partner must make",
                },
                "reason_code": {
                    "type": "string",
                    "description": "Optional structured moderation reason code",
                },
                "version": {
                    "type": "integer",
                    "description": "Optional expected job version for optimistic concurrency",
                },
            },
            "required": ["job_id", "reason"],
        },
        permission_class="confirmation_required",
        persona=[UNIVERSITY_STAFF],
        required_permissions=["authenticated", "role:university_staff", "jobs:moderate"],
        side_effects=[
            "UPDATE jobs (pending_review -> rejected, with reason)",
            "audit job.rejected",
            "notification to posting partner",
        ],
        confirmation_copy=ConfirmationCopy(
            title="Trả lại tin tuyển dụng để chỉnh sửa?",
            body=(
                "Tin tuyển dụng sẽ được trả lại cho đối tác kèm lý do để chỉnh sửa và nộp "
                "lại. Đối tác sẽ được thông báo và hành động này được ghi nhật ký."
            ),
            cta_confirm="Xác nhận trả lại",
        ),
        fallback=(
            "I couldn't send that job back right now. Use /university/moderation/jobs to "
            "review and request changes."
        ),
        audit_event_type="TOOL_REQUEST_JOB_CHANGES",
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
