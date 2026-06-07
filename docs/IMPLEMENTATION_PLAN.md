# Implementation Plan

## Approved Scope

Build the enterprise JD management and rule-based matching module for final/demo-day. The module will use local JSON storage, mock student profiles, Gemini 3.1 Flash Lite for JD parsing, schema validation/edit before saving, FastAPI for APIs, and Streamlit for a thin demo UI.

## Milestones

1. Create docs and evaluation plan.
2. Scaffold Level 3 module structure with backend, optional Streamlit UI, docs, eval, data, and tests.
3. Define schemas for jobs, skills, students, thresholds, and match results.
4. Implement local JSON repositories for jobs and mock students.
5. Implement JD input pipeline: form text, PDF/DOCX extraction, Gemini parser, validation/edit handoff.
6. Implement job management API.
7. Implement rule-based matching engine and configurable thresholds.
8. Add Streamlit demo UI.
9. Run evaluation cases and update evidence.
10. Update README, worklog, and decision log.

## Task List

- [x] Create intake summary.
- [x] Create project brief.
- [x] Create architecture draft.
- [x] Create evaluation plan.
- [x] Create implementation plan.
- [x] Scaffold backend/frontend/data/test structure after user approval.
- [x] Implement schema models and validators.
- [x] Implement JSON storage.
- [x] Implement mock student profile provider.
- [x] Implement PDF/DOCX/TXT text extraction.
- [x] Implement Gemini JD parser with configurable model and fallback parser.
- [x] Implement schema validation and review/edit flow.
- [x] Implement job management endpoints.
- [x] Implement matching engine.
- [x] Implement threshold config.
- [x] Implement Streamlit demo UI.
- [x] Add tests for matching and validation.
- [x] Run core evaluation cases.
- [x] Update README and logs.

## Proposed Structure

```text
project-root/
├── README.md
├── backend/
│   ├── src/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   └── services/
│   └── tests/
├── frontend/
│   └── streamlit_app.py
├── data/
│   ├── jobs/
│   └── mock/
├── docs/
└── eval/
```

## Open Questions

- Confirm final team-facing project/module name if it should differ from Enterprise JD Matching Module.
- Confirm final student API endpoint once the teammate module is ready.
