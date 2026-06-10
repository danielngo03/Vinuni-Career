# Architecture

## Selected Level

Level 3 - Demo Day.

## System Overview

```mermaid
graph TB
    Company["Company / Recruiter"] --> UI["Streamlit UI"]
    UI --> Home["Home Page"]
    UI --> JDPage["JD Workspace Page"]
    JDPage --> ParserFlow["JD Input and Parser Flow"]
    ParserFlow --> Reader["PDF / DOCX / TXT Reader"]
    ParserFlow --> LLM["Configured LLM Provider"]
    ParserFlow --> Fallback["Deterministic Fallback Parser"]
    LLM --> Validator["Schema Validation and Review"]
    Fallback --> Validator
    Validator --> JobStore["Local JSON Job Store"]
    JDPage --> Matcher["Rule-Based Matching Engine"]
    Matcher --> JobStore
    Matcher --> StudentProvider["Mock Student Profile Provider"]
    Matcher --> Results["Ranked Match Results"]
    API["FastAPI App"] --> JDRouter["JD Matching Router"]
    API --> StudentRouter["Student Profile Router Skeleton"]
    JDRouter --> ParserFlow
    JDRouter --> Matcher
    StudentRouter --> StudentProvider
```

## Backend Shape

The backend uses one FastAPI app that composes agent-style routers.

```text
backend/src/
  api/
    main.py              FastAPI app composition
  agents/
    jd_matching/         JD parsing, job management, matching routes
    student_profile/     Small student profile API skeleton
  core/                  settings and paths
  models/                shared dataclasses and validation helpers
  provider/              shared LLM provider adapters
  services/              shared parser, storage, document reader, matching logic
```

This keeps the current demo simple while still giving each future task a clear place to live.

## AI Core

The AI core is the JD parser. It extracts structured job requirements from uploaded or manually entered JD content. Matching decisions are deterministic and are not made by the LLM.

If the selected LLM provider is not configured or fails, the system uses a deterministic fallback parser so the demo remains usable.

## Agents / Modules

| Name | Responsibility |
|------|----------------|
| `jd_matching` | Parse JD, save and manage jobs, run matching for open jobs. |
| `student_profile` | Skeleton API for student profile summaries and future integration. |
| Document reader | Extract text from PDF, DOCX, or TXT uploads. |
| Schema validator | Check required fields, data types, score ranges, and skill requirements. |
| Matching engine | Rank students for one open job using deterministic rules. |
| Student profile provider | Return mock student profiles now; can be replaced by an API provider later. |

## State

| Field | Purpose |
|-------|---------|
| `raw_jd_text` | Text extracted from upload or assembled from form input. |
| `parsed_job_requirement` | Draft JSON returned by LLM or fallback parser. |
| `validated_job_requirement` | Schema-valid JSON after validation and optional user edits. |
| `job_status` | Controls whether a job can be matched. |
| `match_thresholds` | Configurable thresholds for strong, partial, or not match. |
| `student_profiles` | Mock student skill profiles. |

## Core Schemas

### Student Skill Profile

```json
{
  "student_id": "student_001",
  "name": "Mock Student",
  "skills": {
    "Python": {
      "score": 8,
      "confidence": 0.85,
      "evidence": ["Flask API project", "pandas data analysis"]
    }
  }
}
```

### Job Requirement Profile

```json
{
  "job_id": "job_001",
  "company_id": "company_001",
  "title": "Backend Intern",
  "status": "open",
  "employment_type": "internship",
  "location": "Ho Chi Minh City",
  "salary_range": "3-5M VND",
  "benefits": ["Mentorship", "Flexible schedule"],
  "skills": {
    "Python": {
      "required_level": 7,
      "importance": 0.9,
      "required": true
    }
  }
}
```

## Matching Rules

Only jobs with `status = open` can be matched.

Default labels:

- `strong_match`: score `>= 0.80`
- `partial_match`: score `>= 0.60`
- `not_match`: score `< 0.60`

Score:

```text
weighted_score =
sum(min(user_score / required_level, 1) * importance) / sum(importance)
```

Constraint:

- If a student is missing a skill with `required = true` and `importance >= 0.8`, they cannot be labeled `strong_match`.

## Current API

Agent catalog:

- `GET /`
- `GET /agents/jd-matching/health`
- `GET /agents/student-profile/health`

JD matching:

- `POST /jobs/parse`
- `POST /jobs/parse-upload`
- `POST /jobs`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `PATCH /jobs/{job_id}`
- `POST /jobs/{job_id}/open`
- `POST /jobs/{job_id}/close`
- `DELETE /jobs/{job_id}`
- `GET /students/mock`
- `POST /jobs/{job_id}/match`

Student profile skeleton:

- `GET /agents/student-profile/students/{student_id}/summary`

## Frontend

Streamlit UI:

- Home page with project stats and link to JD Workspace.
- JD Workspace page with parse, manage, and matching tabs.

A CV page is intentionally not included yet because real CV parsing/profile work is not implemented.

## Risks

- LLM output can be invalid; schema validation and edit review are required.
- Mock student profiles may not match future API shape exactly; keep provider logic isolated.
- JSON local storage is demo-friendly but not production-safe under concurrent writes.
- Skill aliases can reduce match quality; normalization should keep expanding.
