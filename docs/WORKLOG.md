# Worklog

| Date | Work Done | Result | Next Step |
|------|-----------|--------|-----------|
| 2026-06-07 | Ran VinUni AI Project intake for assigned module | Confirmed enterprise JD management + rule-based matching scope | Ask user to approve plan before scaffolding |
| 2026-06-07 | Drafted planning artifacts | Created intake summary, brief, architecture, evaluation plan, implementation plan, decision log | Scaffold project after approval |
| 2026-06-07 | Implemented approved module scope | Added backend services, FastAPI wrapper, Streamlit UI, mock data, tests, sample JDs, and README | Integrate with real student API when available |
| 2026-06-07 | Ran verification | Pytest, compile, fallback parse/match, and FastAPI TestClient smoke flow passed | Manually verify Streamlit UI and real Gemini key |
| 2026-06-10 | Refactored backend API composition | Added agent-style routers for JD matching and student profile skeleton | Keep future task APIs under `backend/src/agents` |
| 2026-06-10 | Split Streamlit frontend | Added Home dashboard entrypoint, shared helpers, and JD Workspace page | Keep page navigation aligned as new workflows are added |
| 2026-06-10 | Split documentation | README now introduces the topic; run commands moved to `docs/RUNNING.md` | Keep docs aligned with project structure |
| 2026-06-11 | Added CV analysis workflow | CV uploads/text can be parsed into student profile JSON, saved locally, and included in matching | Verify Streamlit manually with a real Gemini key |
| 2026-06-11 | Added basic role authorization | Backend routes use demo role headers; Streamlit uses demo login for enterprise, student, and teacher roles; CV profiles are owner-scoped | Replace demo headers/login with real auth when account management exists |
| 2026-06-12 | Tidied Streamlit frontend structure | Removed duplicate Home page, centralized dashboard links, renamed role-specific pages, parse metadata status, and job review data helpers | Manually smoke-test Streamlit navigation in a browser |
