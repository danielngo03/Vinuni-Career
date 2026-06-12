# Worklog

| Date | Work Done | Result | Next Step |
|------|-----------|--------|-----------|
| 2026-06-07 | Ran project intake and scoped demo-day module | Confirmed enterprise JD management, validated JD parsing, local JSON storage, and `all_students_for_job` matching as the core assignment | Keep course recommendation, admin, production auth, and full deployment out of scope |
| 2026-06-07 | Drafted planning and evaluation docs | Added intake summary, project brief, architecture notes, implementation plan, decision log, evaluation plan, and sample JD direction | Keep docs aligned as implementation changes |
| 2026-06-07 | Implemented initial JD matching module | Added schemas, local JSON job storage, mock student provider, JD parser with LLM/fallback path, matching engine, FastAPI endpoints, Streamlit UI, mock data, and tests | Integrate with student profile data when available |
| 2026-06-07 | Verified initial module behavior | Unit tests, compile checks, fallback parse/match smoke flow, and FastAPI smoke flow passed | Run manual Streamlit checks with a real Gemini key |
| 2026-06-10 | Refactored backend into agent-style routers | Split API composition into `jd_matching` and student-profile agent structure under `backend/src/agents` | Keep future teammate-owned workflows isolated by agent folder |
| 2026-06-10 | Split Streamlit frontend and docs | Added Home/JD page structure and moved run commands into `docs/RUNNING.md` | Keep README as project overview and docs as operating notes |
| 2026-06-11 | Added CV analysis workflow | CV upload/text parsing now creates validated student skill profile JSON saved under `data/students` and usable by matching | Verify CV parsing manually with a real Gemini key |
| 2026-06-11 | Added demo role boundaries | Backend routes use `X-Demo-Role` / `X-Demo-User-Id`; student-owned profiles store `owner_user_id` | Replace demo headers with real auth if productized |
| 2026-06-11 | Added teacher transcript/RAG workflow | Teacher pipeline can build raw transcripts, cleaned transcripts, chunks, and reports under `data/youtube_rag` | Keep RAG data separate from job/student matching data |
| 2026-06-12 | Expanded student profile agent | Added namespaced student profile CRUD, mock profile access, summaries, and ownership checks under `/agents/student-profile` | Connect to a real teammate student profile API when ready |
| 2026-06-12 | Refreshed architecture overview | Reworked `docs/ARCHITECTURE.md` into a higher-level system overview with Users, Streamlit, FastAPI agents, shared services, and local data | Keep endpoint detail in `docs/RUNNING.md` instead of architecture |
| 2026-06-12 | Re-ran backend verification | `scripts\_pyrun.cmd -m unittest discover -s backend\tests -p "test_*.py"` passed 11 tests | Continue manual UI/Gemini validation before demo |
