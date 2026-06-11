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
| 2026-06-10 | Organize backend by agent-style routers | One large FastAPI file vs per-agent routers | Team members may own separate FastAPI tasks | `main.py` composes routers; each agent keeps its own route module |
| 2026-06-10 | Split frontend into Streamlit pages | One long Streamlit file vs multipage UI | JD flow is easier to maintain as its own workspace | Home page links to JD Workspace; CV page is not added until needed |
| 2026-06-11 | Add CV analysis as a separate agent | Fold CV into JD router vs separate agent | CV parsing has its own upload, validation, and student storage workflow | `cv_analysis` creates local student profiles that matching can use with mock profiles |
| 2026-06-11 | Use demo header-based role authorization | Full login/JWT vs demo headers | The project needs basic role boundaries before production auth exists | `X-Demo-Role` gates student and enterprise endpoints; CV profiles store `owner_user_id` |
