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
```

If `GEMINI_API_KEY` is missing or the LLM call fails, JD parsing uses the deterministic fallback parser.

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
POST /jobs/parse
POST /jobs
GET  /jobs
POST /jobs/{job_id}/match
GET  /students/mock
```

## 4. Run Streamlit UI

In another PowerShell terminal:

```powershell
scripts\_pyrun.cmd -m streamlit run frontend\streamlit_app.py
```

The UI currently has:

- Home page: project overview and page links.
- JD Workspace page: parse JD, manage jobs, and run matching.

## 5. Run Tests

```powershell
scripts\_pyrun.cmd -m unittest discover -s backend\tests -p "test_*.py"
```

## Notes

- Run commands from the project root: `K:\Corhort\C2-App-037`.
- Saved jobs are stored under `data/jobs`.
- Mock student profiles are stored in `data/mock/students.json`.
- Frontend and backend can both run locally at the same time.
