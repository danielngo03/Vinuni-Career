# Architecture

## Level

Level 3 - Demo Day.

This architecture favors clear module boundaries, demo-ready behavior, and simple local persistence over production infrastructure. Detailed endpoint lists live in `docs/RUNNING.md`; implementation history lives in `docs/IMPLEMENTATION_PLAN.md` and `docs/WORKLOG.md`.

## System Overview

```mermaid
flowchart LR
    subgraph Users["Users"]
        direction TB
        Company["Company / Recruiter"]
        Student["Student"]
        Teacher["Teacher"]

        Company ~~~ Student
        Student ~~~ Teacher
    end

    subgraph Frontend["Streamlit Frontend"]
        direction TB
        Home["Home"]
        JDPage["JD Workspace"]
        CVPage["CV Analysis"]
        TeacherPage["Teacher RAG Pipeline"]

        Home ~~~ JDPage
        JDPage ~~~ CVPage
        CVPage ~~~ TeacherPage
    end

    subgraph Backend["FastAPI Backend"]
        direction TB
        API["API App"]
        JDAgent["JD Matching Agent"]
        CVAgent["CV Analysis Agent"]
        StudentAgent["Student Profile Agent"]
        TeacherAgent["Teacher RAG Workflow"]
    end

    subgraph Services["Shared Services"]
        direction TB
        Readers["Document / Transcript Readers"]
        LLM["Configured LLM Provider"]
        Validation["Schema Validation"]
        Matching["Rule-Based Matching"]
    end

    subgraph Data["Local Demo Data"]
        direction TB
        JobStore["Job JSON Store"]
        StudentStore["Student JSON Store"]
        MockStore["Mock Student Profiles"]
        RAGStore["YouTube RAG Outputs"]
    end

    Users --> Frontend
    Frontend --> API
    API --> JDAgent
    API --> CVAgent
    API --> StudentAgent
    API --> TeacherAgent

    JDAgent --> Services
    CVAgent --> Services
    TeacherAgent --> Services

    JDAgent --> JobStore
    CVAgent --> StudentStore
    StudentAgent --> StudentStore
    StudentAgent --> MockStore
    TeacherAgent --> RAGStore

    Matching --> JobStore
    Matching --> StudentStore
    Matching --> MockStore
    JDAgent --> Matching
```

## Module Boundaries

| Module | Owns | Notes |
|--------|------|-------|
| `jd_matching` | JD parsing, job lifecycle, and `all_students_for_job` matching. | Company-facing workflow. Jobs must be open before matching. |
| `cv_analysis` | CV upload/text parsing into student skill profiles. | Student-facing extraction workflow. Saves validated profiles locally. |
| `student_profile` | Student profile CRUD, mock profile access, and summaries. | Keeps profile access separate from CV parsing. |
| Teacher RAG workflow | YouTube transcript collection, cleaning, chunking, and reports. | Teacher-owned workflow, separate from matching. |
| Shared services | Readers, LLM provider adapters, validation, storage, and matching logic. | Used by agents when behavior crosses module boundaries. |

The backend is intentionally agent-style: each workflow has its own router under `backend/src/agents/`, while common schemas and utilities stay in `models/`, `services/`, `provider/`, and `core/`.

## Core Data Flow

Company flow:

1. A company enters or uploads a JD in the JD Workspace.
2. The backend extracts text, parses it with the configured LLM or fallback parser, validates the result, and saves a job JSON file.
3. The company opens the job and runs matching.
4. The matching service ranks student profiles with deterministic rules. Demo seed profiles are stored in the same student store and marked with `metadata.is_mock = true`.

Student flow:

1. A student uploads or pastes CV content in the CV Analysis page.
2. The backend extracts skills with the configured LLM or fallback parser.
3. The validated profile is saved in the local student JSON store.
4. The student profile agent can read, update, delete, or summarize saved profiles.

Teacher flow:

1. A teacher submits a YouTube video or playlist source.
2. The transcript pipeline writes raw transcripts, cleaned transcripts, RAG chunks, and run reports.
3. This data is stored separately from job and student matching data.

## Persistence

| Data | Location | Purpose |
|------|----------|---------|
| Jobs | `data/jobs` | Company-created job requirement profiles. |
| Saved students | `data/students` | CV-derived student skill profiles. |
| Jobs | `data/jobs` | Saved jobs and demo seed jobs. Mock rows are marked with `metadata.is_mock = true`. |
| Students | `data/students` | Saved CV-derived profiles and demo seed students. Mock rows are marked with `metadata.is_mock = true`. |
| YouTube RAG outputs | `data/youtube_rag` | Teacher transcript pipeline artifacts. |

Local JSON is a demo choice. It keeps the project easy to run and inspect, but it is not intended for concurrent production writes.

## Auth Boundary

Demo authorization is header-based:

- `enterprise`: JD parsing, job management, matching, and student list/review access.
- `student`: CV parsing and owned student profile management.
- `teacher`: transcript/RAG pipeline workflows.

This is only a role boundary for the demo. It should be replaced by real account/session auth before production use.

## AI Boundary

The LLM is used for structured extraction:

- JD text or form content to job requirement JSON.
- CV text to student skill profile JSON.

Matching is deterministic and explainable. If the LLM provider is not configured or fails, fallback parsers keep the demo usable.

## Integration Risks

- LLM outputs can be malformed, so validation and review remain required.
- Skill naming varies across JDs and CVs, so normalization should continue expanding.
- Mock profiles may differ from a future teammate-owned student API, so profile provider logic should stay isolated.
- Local JSON storage is simple but not production-safe under concurrent writes.
