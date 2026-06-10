# Corhort Backend Agents

Backend agents for a student-job matching platform. The first agent handles enterprise JD parsing and matching. A second `student_profile` agent provides a small independent FastAPI task for student skill summaries.

## Demo

The backend supports:

- JD input by form, raw text, or PDF/DOCX/TXT upload.
- LLM JD parsing through Gemini 3.1 Flash Lite when `GEMINI_API_KEY` is set.
- Deterministic fallback parsing for local demos without an API key.
- UI parser status showing whether Gemini is configured and whether the last parse used Gemini or fallback.
- JSON review/edit before saving a job.
- Local JSON job storage.
- Open/close/delete job management.
- `all_students_for_job` matching against mock student profiles.
- Student profile summary endpoint under its own agent prefix.
- Configurable strong/partial match thresholds.

## Quick Start

Install dependencies:

```powershell
scripts\_pyrun.cmd -m pip install -r requirements.txt
```

Run API:

```powershell
scripts\_pyrun.cmd -m uvicorn backend.src.api.main:app --reload
```

Run Streamlit demo:

```powershell
scripts\_pyrun.cmd -m streamlit run frontend\streamlit_app.py
```

Run tests:

```powershell
scripts\_pyrun.cmd -m unittest discover -s backend\tests -p "test_*.py"
```

## Configuration

Set these in `.env` or your shell:

```text
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.1-flash-lite
STRONG_MATCH_THRESHOLD=0.8
PARTIAL_MATCH_THRESHOLD=0.6
```

If `GEMINI_API_KEY` is missing or parsing fails, the module uses a deterministic fallback parser so the demo can still run.

## API

Agent catalog:

- `GET /` - service health and available agents.
- `GET /agents/jd-matching/health` - JD matching agent health.
- `GET /agents/student-profile/health` - student profile agent health.

JD matching agent:

- `POST /jobs/parse` - parse raw text or form data into draft job JSON.
- `POST /jobs/parse-upload` - parse PDF/DOCX/TXT upload into draft job JSON.
- `POST /jobs` - save validated job JSON.
- `GET /jobs` - list jobs.
- `GET /jobs/{job_id}` - get one job.
- `PATCH /jobs/{job_id}` - replace/edit one job.
- `POST /jobs/{job_id}/open` - mark job open.
- `POST /jobs/{job_id}/close` - mark job closed.
- `DELETE /jobs/{job_id}` - delete job.
- `GET /students/mock` - inspect mock student profiles.
- `POST /jobs/{job_id}/match` - match one open job against mock students.

Student profile agent:

- `GET /agents/student-profile/students/{student_id}/summary` - summarize one mock student profile.

Parse endpoints include an internal `_parser` field in the response so the UI can show whether the result came from Gemini or the fallback parser. Do not include `_parser` when saving a job; it is status metadata, not part of the job schema.

## Project Structure

```text
backend/
  src/
    api/        FastAPI app composition
    agents/
      jd_matching/       routes for JD parsing, job CRUD, matching
      student_profile/   routes and service for student profile summaries
    core/       settings and paths
    models/     schema dataclasses and validators
    provider/   shared LLM provider adapters
    services/   parser, storage, document reader, matching engine
  tests/        unittest coverage for agents and shared logic
data/
  jobs/         local saved jobs
  mock/         mock student profiles
docs/           intake, architecture, implementation, logs
eval/           evaluation plan, sample JDs, report
frontend/       Streamlit demo UI
```

## Adding Another Agent

For a small team where each person owns one FastAPI task, add a new folder under `backend/src/agents/<agent_name>/`:

```text
backend/src/agents/<agent_name>/
  __init__.py
  router.py      FastAPI routes with prefix /agents/<agent-name>
  service.py     agent-specific business logic
```

Then import and include its router in `backend/src/api/main.py`. Keep shared code in `models/`, `services/`, `provider/`, or `core/` only when more than one agent needs it.

## Evaluation

See [eval/EVALUATION_PLAN.md](eval/EVALUATION_PLAN.md) and [eval/EVALUATION_REPORT.md](eval/EVALUATION_REPORT.md).

## Notes

This module intentionally does not implement student CV parsing, course recommendation, RAG interview simulation, admin dashboards, production auth, or a production database.
