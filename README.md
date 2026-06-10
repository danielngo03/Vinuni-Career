# Corhort: Student-Job Matching Demo

Corhort is a demo system for matching student profiles with enterprise job descriptions. The project focuses on the company-side workflow: a company can input a job description, convert it into structured requirements, manage the job status, and run matching against mock student profiles.

## Topic

The topic is an AI-assisted recruitment and internship matching module. It helps transform unstructured job descriptions into validated job requirement data, then compares those requirements with student skill profiles to produce ranked match results.

## Main Goals

- Parse job descriptions from form input, raw text, or uploaded documents.
- Use an LLM provider when configured, with a deterministic fallback for local demos.
- Store and manage job descriptions locally as validated JSON.
- Open or close jobs before running matching.
- Match open jobs against mock student profiles.
- Explain match results with matched skills and missing or weak skills.
- Keep backend features organized by agent-style FastAPI routers so each task can be developed independently.

## Current Scope

Implemented:

- JD parsing and review.
- Job create, list, update, open, close, and delete.
- Rule-based student-job matching.
- Mock student profile loading.
- Streamlit UI with a home page and a JD workspace page.
- Agent-style backend structure for JD matching and a student profile API skeleton.

Not implemented yet:

- Real CV upload and parsing.
- Production database.
- Authentication and authorization.
- Admin dashboard.
- Deployment configuration.

## Project Structure

```text
backend/
  src/
    api/        FastAPI app composition
    agents/     agent-style API routers
    core/       settings and paths
    models/     shared schema dataclasses and validators
    provider/   shared LLM provider adapters
    services/   parser, storage, document reader, matching engine
  tests/        backend tests
data/
  jobs/         local saved jobs
  mock/         mock student profiles
docs/           project docs and run guide
eval/           evaluation plan, sample JDs, report
frontend/       Streamlit demo UI
scripts/        project runner scripts
```

## Documentation

- Run guide: [docs/RUNNING.md](docs/RUNNING.md)
- Architecture notes: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Project brief: [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md)
- Evaluation plan: [eval/EVALUATION_PLAN.md](eval/EVALUATION_PLAN.md)
- Evaluation report: [eval/EVALUATION_REPORT.md](eval/EVALUATION_REPORT.md)
