# Corhort: Student-Job Matching Demo

Corhort is a local MVP for AI-assisted student, enterprise, and teacher workflows.

The app supports:

- Enterprises creating structured job descriptions and running student-job matching.
- Students parsing CVs into skill profiles and matching themselves against open jobs.
- Teachers viewing demo statistics and building RAG-ready transcript data from YouTube videos or playlists.

This repository is designed for a local demo, not production deployment.

## MVP User Flow

Recommended 3-minute demo flow:

1. Log in as `Enterprise / Company`.
2. Open `JD Workspace`, parse or enter a job description, save the job, mark it open, and run matching.
3. Log in as `Student`.
4. Open `CV Analysis`, parse a CV, save the student profile, run job matching, and inspect matched job details.
5. Log in as `Teacher / School`.
6. Open the teacher dashboard to view student/company statistics, then open `Teacher RAG Pipeline` to submit a YouTube video or playlist URL.

## Features

Implemented:

- Demo login with account types: `enterprise`, `student`, and `teacher`.
- JD parsing from text, form input, or uploaded documents.
- LLM parsing through Gemini when configured, with deterministic fallback parsing for local demos.
- Job create, list, update, open, close, delete, and detail views.
- Rule-based student-job matching with score labels, matched skills, and missing/weak skill explanations.
- CV parsing into student skill profiles.
- Student CV review against one open JD, including missing skills, missing keywords, CV rewrite suggestions, and priority actions.
- Student profile create, list, read, update, delete, and summary routes.
- Student-side match run against all open job details.
- Enterprise-side matching against student profiles stored in `data/students`, including profiles marked as mock.
- Teacher dashboard statistics for student and enterprise demo data.
- Teacher YouTube transcript pipeline for video or playlist sources.
- Local JSON storage for jobs, students, and RAG outputs.

Not implemented for production:

- Real account/session authentication.
- Production database.
- Multi-user concurrency controls.
- Deployment configuration.

## Architecture

Architecture and data flow are documented in:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

High-level components:

- `frontend/`: Streamlit entrypoint, dashboard renderer, shared UI helpers, demo auth, and role-specific pages.
- `frontend-web/`: production-style React/Vite frontend that talks to the FastAPI API.
- `backend/src/api/`: FastAPI app composition.
- `backend/src/agents/`: workflow routers for JD matching, CV analysis, and student profiles.
- `backend/src/services/`: parsing, storage, document reading, matching, and YouTube RAG pipeline logic.
- `data/jobs/`: saved job descriptions, including seed records marked with `metadata.is_mock = true`.
- `data/students/`: saved CV-derived student profiles, including seed records marked with `metadata.is_mock = true`.
- `data/youtube_rag/`: raw transcripts, cleaned transcripts, chunks, and reports.

## Project Structure

```text
backend/
  src/
    api/        FastAPI app composition
    agents/     agent-style API routers
    core/       settings, paths, and demo auth helpers
    models/     shared schemas and validators
    provider/   shared LLM provider adapters
    services/   parser, storage, document reader, matching, RAG pipeline
  tests/        backend tests
data/
  jobs/         local saved jobs and mock seed jobs
  students/     local saved student profiles and mock seed students
  youtube_rag/  teacher transcript pipeline outputs
docs/           architecture, project notes, and run guide
eval/           evaluation plan, sample JDs, and evidence report
frontend/       Streamlit demo UI
  Home.py       Streamlit entrypoint
  dashboard.py  role-aware dashboard renderer
  demo_auth.py  demo login helpers
  shared.py     shared UI and repository helpers
  pages/        role-specific workspaces
scripts/        local runner and RAG pipeline scripts
```

## Setup

Run commands from the project root:

```powershell
cd K:\Corhort\C2-App-037
```

Install dependencies:

```powershell
scripts\_pyrun.cmd -m pip install -r requirements.txt
```

Create or update `.env` in the project root.

For local fallback mode, no API key is required. Optional configuration:

```text
GEMINI_API_KEY=your_gemini_key
GEMINI_MODEL=gemini-3.1-flash-lite
STRONG_MATCH_THRESHOLD=0.8
PARTIAL_MATCH_THRESHOLD=0.6
DEMO_AUTH_ENABLED=true
```

If `GEMINI_API_KEY` is missing or the provider call fails, JD and CV parsing use deterministic fallback behavior where available.

## Run Locally

Start FastAPI:

```powershell
scripts\_pyrun.cmd -m uvicorn backend.src.api.main:app --reload
```

FastAPI docs:

```text
http://127.0.0.1:8000/docs
```

Start the production-style React frontend in another terminal:

```powershell
cd frontend-web
npm install
npm run dev
```

Default React URL:

```text
http://127.0.0.1:5173
```

The Streamlit demo remains available as a legacy local UI:

```powershell
scripts\_pyrun.cmd -m streamlit run frontend\Home.py
```

Default Streamlit URL:

```text
http://127.0.0.1:8501
```

## Demo Accounts

The Streamlit UI lets the user choose an account type during demo login.

API requests use demo headers:

```text
X-Demo-Role: enterprise | student | teacher
X-Demo-User-Id: company_demo | mock-student-ai-001 | teacher_demo
```

Role behavior:

- `enterprise`: manage JDs, open/close jobs, run matching, and review student profiles.
- `student`: parse CVs, save owned profile data, and run matching against open jobs.
- `teacher`: view teacher dashboard statistics and build YouTube transcript/RAG data.

This is only a demo authorization boundary. Replace it with real authentication before production use.

## Useful API Endpoints

```text
GET  /
GET  /agents/jd-matching/health
GET  /agents/cv-analysis/health
GET  /agents/student-profile/health
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
POST /jobs/{job_id}/match
POST /students/{student_id}/match-jobs
POST /students/{student_id}/jobs/{job_id}/review

POST /students/cv/parse
POST /students/cv/parse-upload
POST /students
GET  /students
GET  /students/{student_id}
DELETE /students/{student_id}

GET  /agents/student-profile/students/mock
GET  /agents/student-profile/students/{student_id}/summary

POST /agents/teacher-rag/detect
POST /agents/teacher-rag/run
```

## Sample Queries

Parse a JD:

```powershell
$headers = @{
  "X-Demo-Role" = "enterprise"
  "X-Demo-User-Id" = "company_demo"
}

$body = @{
  text = "AI Engineer Intern. Required skills: Python 8, machine learning 7, SQL 5. Nice to have: LLM 6."
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/jobs/parse" -Method Post -Headers $headers -Body $body -ContentType "application/json"
```

Parse a CV:

```powershell
$headers = @{
  "X-Demo-Role" = "student"
  "X-Demo-User-Id" = "mock-student-ai-001"
}

$body = @{
  text = "Student has experience with Python, SQL, machine learning projects, dashboards, and teamwork."
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/students/cv/parse" -Method Post -Headers $headers -Body $body -ContentType "application/json"
```

Run student-side matching after saving a student profile:

```powershell
$headers = @{
  "X-Demo-Role" = "student"
  "X-Demo-User-Id" = "mock-student-ai-001"
}

Invoke-RestMethod -Uri "http://127.0.0.1:8000/students/mock-student-ai-001/match-jobs" -Method Post -Headers $headers
```

Review a saved student profile against one open job:

```powershell
$headers = @{
  "X-Demo-Role" = "student"
  "X-Demo-User-Id" = "mock-student-frontend-001"
}

$body = @{
  use_llm = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/students/mock-student-frontend-001/jobs/mock-frontend-intern-001/review" -Method Post -Headers $headers -Body $body -ContentType "application/json"
```

## Teacher RAG Pipeline

Teachers can build RAG-ready transcript data from either:

- A single YouTube video URL.
- A YouTube playlist URL.

Use the Streamlit `Teacher RAG Pipeline` page after logging in as `Teacher / School`, or run the CLI:

```powershell
python scripts\mit_rag_pipeline.py run --source-url "https://www.youtube.com/watch?v=0Va2dOLqUfM" --teacher-user-id teacher_001 --category "Biology & Chemistry" --course-title "Chemistry Principles"
```

Outputs are written under `data/youtube_rag`:

```text
raw/<source>/videos/<video_id>.json
cleaned/<source>/videos/<video_id>.json
chunks/<source>.jsonl
reports/<run_id>.json
```

## Evaluation Evidence

Evaluation docs:

- [eval/EVALUATION_PLAN.md](eval/EVALUATION_PLAN.md)
- [eval/EVALUATION_REPORT.md](eval/EVALUATION_REPORT.md)

For manual evidence, prepare at least:

- 2 JDs.
- 3 CVs.
- 1 YouTube video or playlist URL if teacher RAG evidence is included.

Recommended manual cases:

1. Enterprise parses, saves, opens, and views a JD.
2. Student parses and saves a CV profile.
3. Student runs match against open JDs and views job detail output.
4. Enterprise runs matching for one JD and verifies ranked student results.
5. Teacher views dashboard statistics and runs or previews the RAG pipeline flow.

Each manual case should record the input, steps, actual output, and pass/fail result.

## Tests

Run backend tests:

```powershell
scripts\_pyrun.cmd -m unittest discover -s backend\tests -p "test_*.py"
```

## Additional Documentation

- Run guide: [docs/RUNNING.md](docs/RUNNING.md)
- Architecture notes: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Project brief: [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md)
