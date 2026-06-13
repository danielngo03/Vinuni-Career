# Decision Log

| Date | Decision | Options Considered | Reason | Consequence |
|------|----------|--------------------|--------|-------------|
| 2026-06-07 | Scope module to enterprise JD management and `all_students_for_job` matching | Full platform vs assigned module | User is assigned enterprise side and rule-based matching | Avoids unrelated student/admin/RAG/course work |
| 2026-06-07 | Use Level 3 - Demo Day | Level 1, Level 2, Level 3 | Final/demo-day project needs clearer APIs, eval evidence, and demo readiness | Use backend/frontend split, but keep UI thin |
| 2026-06-07 | Use mock student profiles first | Wait for student API vs mock provider | Student module is owned by another teammate and may not be ready | Matching can be demoed and evaluated independently |
| 2026-06-07 | Store jobs in local JSON | SQLite/database vs local JSON | User requested JSON local for now | Fast demo implementation, not production concurrency-safe |
| 2026-06-07 | Use Gemini 3.1 Flash Lite for JD parsing | Gemini vs other LLMs vs no LLM | User specified Gemini 3.1 Flash Lite | Model configured through environment/config |
| 2026-06-07 | Validate and allow edit after parsing | Save raw LLM output vs validate/edit | LLM output can be malformed or incomplete | Adds a required review step before saving/matching |
| 2026-06-07 | Keep course recommendations out of scope | Include suggested courses vs missing skills only | User said course recommendation is not in this task | Match result focuses on missing/weak skills |
| 2026-06-10 | Organize backend by agent-style routers | One large FastAPI file vs per-workflow routers | Team members may own separate FastAPI tasks | `main.py` composes routers; each FastAPI workflow keeps its own route module |
| 2026-06-10 | Split frontend into role-specific Streamlit pages | One long Streamlit file vs multipage UI | Role-specific workflows are easier to maintain as separate workspaces | Home dashboard links to enterprise, student, and teacher workspaces |
| 2026-06-11 | Add CV analysis as a separate workflow router | Fold CV into JD router vs separate router | CV parsing has its own upload, validation, and student storage workflow | `cv_analysis` creates local student profiles that matching can use alongside mock profiles |
| 2026-06-11 | Use demo header-based role authorization | Full login/JWT vs demo headers | The project needs basic role boundaries before production auth exists | `X-Demo-Role` gates student, enterprise, and teacher demo flows; CV profiles store `owner_user_id` |
| 2026-06-12 | Keep one Streamlit Home entrypoint | Duplicate Home page under `pages/` vs a single top-level entrypoint | Streamlit multipage navigation becomes confusing when Home appears twice | Run the UI from `frontend/Home.py`; workspace pages link back to that entrypoint |
| 2026-06-12 | Keep Teacher RAG as a shared service for now | Add teacher FastAPI router vs Streamlit/CLI service call | The current teacher workflow is a local transcript build pipeline, not an API integration point yet | Streamlit and CLI call `youtube_rag_pipeline.py` directly; add a router later if another client needs it |
