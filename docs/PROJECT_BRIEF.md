# Project Brief

## Project Name

Corhort Student-Job Matching Demo

## Level

Level 3 - Demo Day

## Problem

Companies need a structured way to create job requirements and discover which students are suitable, while the platform avoids exposing all student contact information directly. Raw JDs are inconsistent, so the system needs to convert them into a normalized JSON profile before matching.

## Target User

Company or recruiter users managing job requests in a student-job matching platform.

## Demo Goal

In the demo, a company user can:

- Upload or enter a JD.
- Convert it into validated job requirement JSON.
- Review/edit the JSON.
- Save the job request.
- Open or close the job.
- Run matching for an open job and see ranked mock students with missing skills and explanations.

## AI Core

Parse JD content into a structured job requirement profile using Gemini 3.1 Flash Lite. The parser should extract metadata and skill requirements, then pass the output through schema validation before the job is saved.

## Inputs

- PDF/DOCX JD upload.
- Structured JD form fields.
- Local mock student skill profiles.
- Optional threshold settings for match labels.

## Outputs

- `job_requirement.json`.
- Saved job request JSON.
- Ranked match results for one open job.
- Missing or weak skill explanations per student.

## Scope

- Enterprise-side JD creation and management.
- Student CV analysis into skill profiles for matching.
- LLM JD parsing.
- LLM CV parsing.
- JSON validation and edit flow.
- Local JSON storage.
- Rule-based `all_students_for_job` matching.
- Mock student profile provider.
- Agent-style FastAPI backend.
- Streamlit home page and JD workspace page.

## Non-Goals

- Course recommendations.
- Interview RAG.
- Admin dashboards.
- Production auth and database.
- Deployment hardening beyond demo readiness.

## Timebox

Final/demo-day module. Build the smallest reliable module that can be integrated and evaluated by the team.
