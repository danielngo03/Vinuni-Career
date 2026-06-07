# Intake Summary

## Project Idea

Build the enterprise-side module for a student-job matching platform. Companies can create job descriptions, have them parsed into structured job requirement JSON by an LLM, manage job request status, and run rule-based matching against student skill profiles.

## User Goal

Deliver the assigned module for a final/demo-day project: enterprise job request management plus `all_students_for_job` matching.

## Target User

- Primary: company / recruiter users who create and manage job requests.
- Secondary: project team members who need a stable API/module to integrate with student profile and admin modules.

## Selected Direction

Scope is limited to:

- Enterprise JD input and management.
- LLM-based JD parsing.
- JSON validation/edit before saving.
- Rule-based matching from one open JD to ranked student profiles.
- Mock student profiles until the student module API is ready.

## Recommended Level

Level 3 - Demo Day.

## Why This Level

This is final/demo-day material and needs clear APIs, evaluation evidence, demo-ready behavior, and maintainable module boundaries. The implementation should still avoid full product hardening because the assigned scope is one module, not the full platform.

## Scope

- Upload JD as PDF or DOCX and extract text.
- Enter JD through a structured form/template.
- Parse JD text/form data into `job_requirement.json` with Gemini 3.1 Flash Lite.
- Validate parsed JSON against the required schema.
- Allow users to review and edit parsed JSON before saving.
- Store job requests in local JSON files.
- Support create, list, view, update, open, close, and delete job requests.
- Match only jobs with `status = open`.
- Match one job against mock student profiles.
- Return ranked students with `match_score`, `match_status`, matched skills, missing or weak skills, and explanation.
- Allow configurable matching thresholds.
- Provide a thin FastAPI backend and simple Streamlit demo UI.

## Non-Goals

- Student CV upload or CV parsing.
- Student profile generation.
- Course recommendation.
- RAG interview simulation.
- School/admin dashboard.
- Full auth or production permissions.
- Production database.
- Next.js frontend.
- Full contact workflow between companies and students.

## AI Agent Core

The AI core is a JD extraction parser, not a general chatbot. It receives raw JD text or structured form data and returns a normalized job requirement profile. Rule-based matching remains deterministic and explainable.

## Data, Tools, Or RAG

- LLM: Gemini 3.1 Flash Lite.
- Document readers: PDF and DOCX text extraction.
- Storage: local JSON files.
- Student profiles: mock JSON provider first, later replaceable with an API provider.
- RAG: not in scope for this module.

## Backend / Frontend Need

- Backend: FastAPI.
- Frontend/demo: Streamlit.
- Keep both thin; the main value is the parser, schema validation, job state management, and matching engine.

## Evaluation Direction

Evaluate with mock JDs and mock student profiles:

- JD parser returns valid schema.
- Job status rules are respected.
- Matching scores are explainable and correctly ranked.
- Required high-importance missing skills prevent `strong_match`.
- Threshold customization changes match labels predictably.

## Additional User Notes

- Student profiles will be mocked for now.
- JD storage should be local JSON.
- Course recommendations are outside this task.
- Matching flow should be `all_students_for_job`.
- Thresholds should be editable by the company/admin/demo user.
- JSON validation/edit after Gemini parsing is required.

## Assumptions

- Gemini API key/model access will be provided through environment variables.
- Exact Gemini model id may be configurable if the SDK uses a different model name.
- The future student API can provide at least the skill profile fields already defined by the user.
- Mock data is acceptable for evaluation and demo until integration.

## Risks Or Concerns

- Gemini output may be malformed or incomplete, so schema validation and review/edit are required.
- Skill names can vary across CVs and JDs, so skill normalization is needed.
- Student API dependency can block integration; provider abstraction should isolate this.
- JSON local storage is fine for demo but not safe for concurrent production use.

## Unresolved Decisions

- Final project/module name.
- Final endpoint naming convention if the team already has one.
- Final student API endpoint once teammate implementation is ready.

## Confirmation

User confirmed this summary on 2026-06-07, with explicit confirmation to include JSON validation/edit after Gemini parsing.
