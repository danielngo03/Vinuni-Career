# Running The Project

This guide explains how to run the Corhort demo locally on Windows PowerShell.

## 1. Install Dependencies

From the project root:

```powershell
scripts\_pyrun.cmd -m pip install -r requirements.txt
```

## 2. Configure Environment

Create or update `.env` in the project root. For local fallback mode, no API key is required.

Optional LLM configuration:

```text
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.1-flash-lite
STRONG_MATCH_THRESHOLD=0.8
PARTIAL_MATCH_THRESHOLD=0.6
DEMO_AUTH_ENABLED=true
```

If `GEMINI_API_KEY` is missing or the LLM call fails, JD and CV parsing use deterministic fallback behavior where available.

Demo API requests use role headers. The Streamlit demo uses the same role/account values in its local login state.

```text
X-Demo-Role: enterprise
X-Demo-User-Id: company_demo
```

or:

```text
X-Demo-Role: student
X-Demo-User-Id: mock-student-ai-001
```

Teacher/school demo accounts use:

```text
X-Demo-Role: teacher
X-Demo-User-Id: teacher_demo
```

## 3. Run Backend API

```powershell
scripts\_pyrun.cmd -m uvicorn backend.src.api.main:app --reload
```

Default API docs:

```text
http://127.0.0.1:8000/docs
```

Useful endpoints:

```text
GET  /
GET  /agents/jd-matching/health
GET  /agents/student-profile/health
GET  /agents/cv-analysis/health
GET  /agents/teacher-rag/health
POST /jobs/parse
POST /jobs/parse-upload
POST /jobs
GET  /jobs
GET  /jobs/open
GET  /jobs/{job_id}
PATCH /jobs/{job_id}
POST /jobs/{job_id}/open
POST /jobs/{job_id}/close
DELETE /jobs/{job_id}
POST /jobs/{job_id}/match
POST /students/{student_id}/match-jobs
POST /students/{student_id}/jobs/{job_id}/review
GET  /students/mock
POST /students/cv/parse
POST /students/cv/parse-upload
POST /students
GET  /students
GET  /students/{student_id}
DELETE /students/{student_id}
POST /agents/student-profile/students
GET  /agents/student-profile/students
GET  /agents/student-profile/students/mock
GET  /agents/student-profile/students/{student_id}
PATCH /agents/student-profile/students/{student_id}
DELETE /agents/student-profile/students/{student_id}
GET  /agents/student-profile/students/{student_id}/summary
POST /agents/teacher-rag/detect
POST /agents/teacher-rag/run
```

Role rules:

- `enterprise`: JD parsing, job management, matching, and student list access.
- `student`: CV parsing, saving a student profile, managing owned profiles, matching owned profiles against open jobs, and reviewing an owned CV profile against one open JD.
- Student profile CRUD is namespaced under `/agents/student-profile`; students can manage their own saved profiles, while enterprises can read profiles for matching/review.
- `teacher`: YouTube transcript RAG pipeline API and UI for school-owned course data.

## 4. Run React Web UI

In another PowerShell terminal:

```powershell
cd frontend-web
npm install
npm run dev
```

Default URL:

```text
http://127.0.0.1:5173
```

The React app calls FastAPI at `http://127.0.0.1:8000` by default. To point it elsewhere, create `frontend-web/.env`:

```text
VITE_API_BASE_URL=http://127.0.0.1:8001
```

## 5. Run Legacy Streamlit UI

In another PowerShell terminal:

```powershell
scripts\_pyrun.cmd -m streamlit run frontend\Home.py
```

The UI currently has:

- Home page: demo login, role-aware dashboard metrics, and page links.
- Enterprise JD Workspace page: parse JD, manage jobs, and run matching.
- Student CV Analysis page: parse CVs, review and save student profiles, match the student against open jobs, and review a CV profile against a selected open JD.
- Teacher RAG Pipeline page: build transcript/RAG data from a YouTube video or playlist.

## 6. Run Tests

```powershell
scripts\_pyrun.cmd -m unittest discover -s backend\tests -p "test_*.py"
```

## 7. Build YouTube RAG Transcript Data

For a single video or playlist URL:

```powershell
scripts\_pyrun.cmd scripts\mit_rag_pipeline.py run --source-url "https://www.youtube.com/watch?v=0Va2dOLqUfM" --teacher-user-id teacher_001 --category "Biology & Chemistry" --course-title "Chemistry Principles"
```

The same command accepts playlist URLs. Outputs are written under `data/youtube_rag` by default:

```text
raw/<source>/videos/<video_id>.json
cleaned/<source>/videos/<video_id>.json
chunks/<source>.jsonl
reports/<run_id>.json
```

Teachers can also use the Streamlit `Teacher RAG Pipeline` page after logging in with account type `teacher`.

## Notes

- Run commands from the project root: `K:\Corhort\C2-App-037`.
- Saved jobs are stored under `data/jobs`.
- Saved CV-derived student profiles are stored under `data/students`.
- Mock jobs are stored in `data/jobs` with `metadata.is_mock = true`.
- Mock student profiles are stored in `data/students` with `metadata.is_mock = true`.
- YouTube RAG transcript outputs are stored under `data/youtube_rag`.
- Frontend and backend can both run locally at the same time.
