# Implementation Plan

## Approved Scope

Build the enterprise JD management and rule-based matching module for final/demo-day. The module uses local JSON storage, mock student profiles, a configurable LLM provider for JD parsing, schema validation/edit before saving, FastAPI for APIs, and Streamlit for a thin demo UI.

## Current Status

The original demo scope is implemented. The backend has since been refactored into agent-style routers, the frontend has been split into Streamlit pages behind a role-based demo login, CV parsing creates local student skill profiles for matching, and teachers can run the YouTube transcript/RAG pipeline from Streamlit.

## Completed Milestones

1. Created docs and evaluation plan.
2. Scaffolded backend, frontend, docs, eval, data, and tests.
3. Defined schemas for jobs, skills, students, thresholds, and match results.
4. Implemented local JSON repositories for jobs and students, including seed records marked with `metadata.is_mock = true`.
5. Implemented JD input pipeline: form text, PDF/DOCX/TXT extraction, LLM parser, fallback parser, validation/edit handoff.
6. Implemented job management API.
7. Implemented rule-based matching engine and configurable thresholds.
8. Added Streamlit demo UI.
9. Added backend tests.
10. Refactored backend routes into agent-style modules.
11. Split frontend into a Home dashboard entrypoint and role-specific workspaces.
12. Split README introduction from the run guide.
13. Added CV analysis agent, local student profile storage, Streamlit CV page, and matching against saved CV-derived students.
14. Added teacher dashboard/RAG pipeline flow, removed legacy Streamlit entrypoints, and renamed role-specific pages.

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
        cv_analysis/
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
    Home.py
    dashboard.py
    demo_auth.py
    shared.py
    pages/
      1_Enterprise_JD_Workspace.py
      2_Student_CV_Analysis.py
      3_Teacher_RAG_Pipeline.py
  data/
    jobs/
    students/
    mock/
    youtube_rag/
  docs/
    RUNNING.md
  eval/
```

## Remaining Integration Work

- Connect to a real student profile API when the teammate module is ready.
- Decide whether local JSON storage should be replaced for a production-like demo.
- Manually verify Streamlit UI with a real Gemini key for JD and CV parsing.
- Manually verify the teacher YouTube transcript pipeline with a stable public video or playlist.

## Development Rule For New Agents

For each new task or teammate-owned API, add a folder under `backend/src/agents/<agent_name>/`:

```text
backend/src/agents/<agent_name>/
  __init__.py
  router.py
  service.py
```

Then include the router in `backend/src/api/main.py`. Shared code should only move into `models/`, `services/`, `provider/`, or `core/` when more than one agent needs it.
