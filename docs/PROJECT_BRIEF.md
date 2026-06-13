# Project Brief

## Project Name

Corhort Student-Job Matching Demo

## Level

Level 3 - Demo Day

## Problem

Companies need a structured way to create job requirements and discover which students are suitable, while the platform avoids exposing all student contact information directly. Raw JDs are inconsistent, so the system needs to convert them into a normalized JSON profile before matching.

## Target User

Company/recruiter users managing job requests, students managing CV-derived profiles, and teacher/school users preparing transcript data for learning workflows.

## Demo Goal

In the demo, users can:

- Companies upload or enter a JD, convert it into validated job requirement JSON, save it, open or close it, and run matching.
- Students upload or paste a CV, save a skill profile, and match themselves against open jobs.
- Teachers view dashboard statistics and build YouTube transcript/RAG data for a video or playlist.

## AI Core

Parse JD and CV content into structured profiles using Gemini 3.1 Flash Lite when configured, with local fallback behavior for demos. The parsers extract metadata and skill requirements, then pass output through schema validation before data is saved.

## Inputs

- PDF/DOCX JD upload.
- PDF/DOCX CV upload.
- Structured JD form fields.
- Local mock student skill profiles.
- Optional threshold settings for match labels.
- YouTube video or playlist URL for teacher transcript/RAG data.

## Outputs

- `job_requirement.json`.
- Saved job request JSON.
- Ranked match results for one open job.
- Missing or weak skill explanations per student.
- Saved CV-derived student skill profiles.
- YouTube transcript chunks and pipeline reports.

## Scope

- Enterprise-side JD creation and management.
- Student CV analysis into skill profiles for matching.
- LLM JD parsing.
- LLM CV parsing.
- JSON validation and edit flow.
- Local JSON storage.
- Rule-based `all_students_for_job` matching.
- Mock student profile provider.
- Agent-style FastAPI backend for JD, CV, and student profile workflows.
- Streamlit demo login, Home dashboard, JD Workspace, CV Analysis, and Teacher RAG Pipeline pages.

## Non-Goals

- Course recommendations.
- Production interview RAG/chat experience.
- Admin dashboards.
- Production auth and database.
- Deployment hardening beyond demo readiness.

## Timebox

Final/demo-day module. Build the smallest reliable module that can be integrated and evaluated by the team.
