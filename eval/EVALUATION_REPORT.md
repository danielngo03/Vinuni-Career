# Evaluation Report

## Run Summary

Date: 2026-06-07

## Checks Run

| Check | Result | Notes |
|-------|--------|-------|
| Python compile | Pass | `scripts\_pyrun.cmd -m compileall backend frontend` |
| Unit tests | Pass | `scripts\_pyrun.cmd -m pytest -q` ran 3 tests |
| Smoke parse + match | Pass | Parsed `eval/sample_jds/backend_intern.txt` with fallback parser and matched against 5 mock students |
| API smoke flow | Pass | FastAPI TestClient parse -> save -> match -> delete returned `200 200 5 student_001` |
| Dependency install | Pass | Dependencies installed into the Python runtime used by `scripts\_pyrun.cmd` |

## Current Evidence

- Matching ranks students by weighted skill score.
- Missing high-importance required skills block `strong_match`.
- Closed jobs cannot be matched.
- Thresholds are configurable.
- TXT upload/text extraction works in the core document reader.
- FastAPI can import `backend.src.api.main:app`.
- Core API flow works with mock data.

## Remaining Manual Demo Checks

- Run Streamlit and verify upload/form/review/save/match workflow visually.
- Test Gemini parsing with a real `GEMINI_API_KEY`.
- Test PDF/DOCX extraction with real JD files.
