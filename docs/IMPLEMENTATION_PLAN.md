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
- [ ] Scaffold backend/frontend/data/test structure after user approval.
- [ ] Implement Pydantic models.
- [ ] Implement JSON storage.
- [ ] Implement mock student profile provider.
- [ ] Implement PDF/DOCX text extraction.
- [ ] Implement Gemini JD parser with configurable model.
- [ ] Implement schema validation and review/edit flow.
- [ ] Implement job management endpoints.
- [ ] Implement matching engine.
- [ ] Implement threshold config.
- [ ] Implement Streamlit demo UI.
- [ ] Add tests for matching and validation.
- [ ] Run evaluation cases.
- [ ] Update README and logs.

## Proposed Structure

```text
project-root/
├── README.md
├── backend/
│   ├── src/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── services/
│   │   └── agent/
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

- Confirm final project/module name.
- Confirm whether to use the endpoint names proposed in `docs/ARCHITECTURE.md`.
- Confirm whether to scaffold now.
