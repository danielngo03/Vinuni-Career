# Implementation Plan

## Approved Scope

Build the enterprise JD management and rule-based matching module for final/demo-day. The module uses local JSON storage, mock student profiles, a configurable LLM provider for JD parsing, schema validation/edit before saving, FastAPI for APIs, and Streamlit for a thin demo UI.

## Current Status

The original demo scope is implemented. The backend has since been refactored into agent-style routers, and the frontend has been split into a Streamlit home page plus a JD Workspace page.

## Completed Milestones

1. Created docs and evaluation plan.
2. Scaffolded backend, frontend, docs, eval, data, and tests.
3. Defined schemas for jobs, skills, students, thresholds, and match results.
4. Implemented local JSON repositories for jobs and mock students.
5. Implemented JD input pipeline: form text, PDF/DOCX/TXT extraction, LLM parser, fallback parser, validation/edit handoff.
6. Implemented job management API.
7. Implemented rule-based matching engine and configurable thresholds.
8. Added Streamlit demo UI.
9. Added backend tests.
10. Refactored backend routes into agent-style modules.
11. Split frontend into home page and JD Workspace.
12. Split README introduction from the run guide.

## Current Structure

```text
project-root/
  README.md
  backend/
    src/
      api/
        main.py
      agents/
        jd_matching/
          router.py
        student_profile/
          router.py
          service.py
      core/
      models/
      provider/
      services/
    tests/
  frontend/
    streamlit_app.py
    shared.py
    pages/
      1_JD_Workspace.py
  data/
    jobs/
    mock/
  docs/
    RUNNING.md
  eval/
```

## Remaining Integration Work

- Connect to a real student profile API when the teammate module is ready.
- Add a CV page only after CV upload/parsing or real profile work exists.
- Decide whether local JSON storage should be replaced for a production-like demo.
- Manually verify Streamlit UI with a real Gemini key.

## Development Rule For New Agents

For each new task or teammate-owned API, add a folder under `backend/src/agents/<agent_name>/`:

```text
backend/src/agents/<agent_name>/
  __init__.py
  router.py
  service.py
```

Then include the router in `backend/src/api/main.py`. Shared code should only move into `models/`, `services/`, `provider/`, or `core/` when more than one agent needs it.
