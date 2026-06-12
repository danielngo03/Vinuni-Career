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

Demo API authorization uses request headers:

```text
X-Demo-Role: enterprise
X-Demo-User-Id: company_demo
```

or:

```text
X-Demo-Role: student
X-Demo-User-Id: mock-student-ai-001
```

Teacher/school accounts use:

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
POST /jobs/parse
POST /jobs
GET  /jobs
POST /jobs/{job_id}/match
GET  /students/mock
POST /students/cv/parse
POST /students/cv/parse-upload
POST /students
GET  /students
POST /agents/student-profile/students
GET  /agents/student-profile/students
GET  /agents/student-profile/students/mock
GET  /agents/student-profile/students/{student_id}
PATCH /agents/student-profile/students/{student_id}
DELETE /agents/student-profile/students/{student_id}
GET  /agents/student-profile/students/{student_id}/summary
```

Role rules:

- `enterprise`: JD parsing, job management, matching, and student list access.
- `student`: CV parsing, saving a student profile, and managing owned profiles.
- Student profile CRUD is namespaced under `/agents/student-profile`; students can manage their own saved profiles, while enterprises can read profiles for matching/review.
- `teacher`: YouTube transcript RAG pipeline page for school-owned course data.

## 4. Run Streamlit UI

In another PowerShell terminal:

```powershell
scripts\_pyrun.cmd -m streamlit run frontend\Home.py
```

The UI currently has:

- Home page: demo login, role-aware dashboard metrics, and page links.
- Enterprise JD Workspace page: parse JD, manage jobs, and run matching.
- Student CV Analysis page: parse CVs, review and save student profiles, and match the student against open jobs.
- Teacher RAG Pipeline page: build transcript/RAG data from a YouTube video or playlist.

## 5. Run Tests

```powershell
scripts\_pyrun.cmd -m unittest discover -s backend\tests -p "test_*.py"
```

## 6. Build YouTube RAG Transcript Data

For a single video or playlist URL:

```powershell
python scripts\mit_rag_pipeline.py run --source-url "https://www.youtube.com/watch?v=0Va2dOLqUfM" --teacher-user-id teacher_001 --category "Biology & Chemistry" --course-title "Chemistry Principles"
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
