# Environment Variables — VinUni Career Platform

> Purpose: canonical local/dev environment variable names. Do not put real secrets in this file.

---

## 1. Environment Philosophy

- Development runs local-first. Do not require Docker for the app runtime.
- Use lightweight dependencies first; heavier services are optional and feature-flagged.
- Root `.env` and root `.env.example` are reserved for AI hook logging only.
- Backend runtime secrets/config live in `backend/.env`; backend placeholders live in `backend/.env.example`.
- Frontend runtime config lives in `frontend/.env`; frontend placeholders live in `frontend/.env.example`.
- `.env` and `.env.*` are local secrets and ignored by git.
- `.env.example` files may contain placeholders only.
- Never write production secrets into docs, tests, fixtures, prompts, migrations, or frontend bundles.
- If a secret is pasted into chat/logs/output, rotate it.

---

## 2. App Runtime

```bash
APP_ENV=local
APP_NAME=vinuni-career-platform
APP_URL=http://localhost:8000
LOG_LEVEL=INFO
DEBUG=true
TIMEZONE=Asia/Ho_Chi_Minh
DEFAULT_LOCALE=vi
SUPPORTED_LOCALES=vi,en
DEFAULT_COUNTRY=VN
```

Rules:

- `DEBUG` is boolean only (`true`, `false`, `1`, `0`). Do not use values such
  as `release`, `prod`, or `local`; use `APP_ENV` for environment names.
- Test shells must not inherit a non-boolean `DEBUG`. If the parent shell has
  `DEBUG=release` or any non-boolean value, override test commands with
  `DEBUG=false` and record the env issue in the handoff.

Locale policy:

- First visit: infer `vi` for Vietnam/Vietnamese browser preference, otherwise `en`.
- Store explicit user choice in profile preferences; explicit choice always wins.
- Backend stores canonical locale as `vi` or `en`; frontend uses route locale.

---

## 3. Local Data Services

```bash
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/vinuni_career
REDIS_URL=redis://localhost:6379/0
TEST_DATABASE_URL=sqlite+aiosqlite:///:memory:
PGVECTOR_ENABLED=true
```

Rules:

- Local Postgres is preferred for pgvector/RBAC/integration tests.
- SQLite/in-memory is allowed only for narrow unit tests that do not depend on Postgres features.
- Redis is optional in early Phase 0; if unavailable, use in-process fallback for local smoke tests only.

---

## 4. Storage And File Processing

```bash
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=.dev/storage
OBJECT_STORAGE_ENDPOINT=http://localhost:9000
OBJECT_STORAGE_ACCESS_KEY=replace-with-local-key
OBJECT_STORAGE_SECRET_KEY=replace-with-local-secret
SIGNED_URL_TTL_SECONDS=900
MAX_UPLOAD_MB=50
```

Rules:

- Local filesystem storage is acceptable for Phase 0/1.
- Object storage adapter must exist behind an interface so MinIO/S3 can be enabled later.
- Direct storage paths never appear in API responses or logs.

---

## 5. Lightweight OCR And Document Extraction

```bash
LOCAL_OCR_ENGINE=auto
CV_NATIVE_PDF_ENGINE=pymupdf4llm
PDF_TEXT_ENGINE=pymupdf4llm
CV_LAYOUT_ENGINE=pymupdf4llm
DOCX_TEXT_ENGINE=python-docx
OCR_FALLBACK_ENGINE=tesseract
CV_OCR_ENGINE=tesseract
TESSERACT_OCR_LANGS=vie+eng
PADDLE_OCR_ENABLED=false
PADDLE_OCR_PREWARM_ENABLED=false
CV_LLM_STRUCTURING_ENABLED=false
CV_EXTRACTION_MAX_PAGES=6
CV_EXTRACTION_MAX_SECONDS=25
```

Default policy:

- Use text-native extraction first: PyMuPDF/PyMuPDF4LLM for PDF when
  available, `pdfplumber` fallback, `python-docx` for DOCX, plain UTF-8 for TXT.
- Use layout-aware extraction when native text is sparse, disordered,
  multi-column, or canvas/vector-heavy.
- Use Tesseract only when native/layout extraction is empty or low quality.
- Use `vie+eng` for OCR because product language is Vietnamese + English.
- Docling/Marker/PaddleOCR or heavier OCR/layout engines are disabled by
  default and only enabled for targeted local experiments or after ADR approval.
- AI CV parsing receives extracted text, never raw PDF bytes.

---

## 6. AI Provider Smoke Tests

```bash
OPENROUTER_API_KEY=replace-with-local-key
AI_DEFAULT_PROVIDER=openrouter
AI_DEFAULT_MODEL_ALIAS=chat_cheap
AI_REASONING_MODEL_ALIAS=reasoning_cheap
AI_EMBEDDING_MODEL_ALIAS=embedding_cheap
AI_EVAL_MODEL_ALIAS=eval_cheap
AI_REAL_CALLS_ENABLED=false
AI_MAX_REAL_CALLS_PER_TEST_RUN=3
AI_DAILY_COST_LIMIT_USD=3.00
# Production: set a Fernet key for admin-managed encrypted provider API keys.
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
AI_PROVIDER_KEY_ENCRYPTION_KEY=replace-with-fernet-key
```

Policy:

- Unit tests and CI use offline/fake providers.
- Use OpenRouter/DeepSeek-compatible low-cost/free aliases for local smoke tests.
- Real model calls are opt-in, small, and documented in test output.
- Do not run a real model call just because `OPENROUTER_API_KEY` exists. First
  pass offline evals and targeted tests; then run only the smallest useful smoke
  sample with `AI_REAL_CALLS_ENABLED=true` and `AI_MAX_REAL_CALLS_PER_TEST_RUN`
  set to 1-3.
- Real AI smoke tests must use internal aliases (`chat_cheap`,
  `reasoning_cheap`, `eval_cheap`, `embedding_cheap`) and must never print the
  concrete key, provider, model, raw prompt, or PII-bearing response.
- Admin-managed provider API keys are accepted only as write-only inputs and are
  stored encrypted with `AI_PROVIDER_KEY_ENCRYPTION_KEY`; env keys remain an ops
  fallback for existing deployments.
- End users never see provider names, model names, token counts, latency, prompts, raw confidence, or internal status.

---

## 7. Auth, Sessions, And Devices

```bash
JWT_SECRET_KEY=replace-with-local-secret
ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=30
SESSION_DEVICE_LIMIT=10
ADMIN_TOTP_REQUIRED=false
ACCOUNT_LOCKOUT_FAILURES=5
ACCOUNT_LOCKOUT_MINUTES=15
GEOIP_ENABLED=false
GEOIP_CITY_LEVEL_ONLY=true
```

Rules:

- Store hashed refresh tokens, not raw tokens.
- Store device hints and IP hashes, not raw full user agents or raw IPs.
- Users can view device sessions and remote logout.
- Exact location is never required for core career workflows.

---

## 8. Email, Notification, And Templates

```bash
EMAIL_PROVIDER=local
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USERNAME=
SMTP_PASSWORD=
EMAIL_FROM_ADDRESS=career@vinuni.edu.vn
EMAIL_FROM_NAME=VinUni Career Center
NOTIFICATION_EMAIL_ENABLED=true
NOTIFICATION_PUSH_ENABLED=false
NOTIFICATION_DIGEST_ENABLED=true
EMAIL_TEMPLATE_EDITOR_ENABLED=true
```

Rules:

- Local dev uses Mailpit or console email.
- Admin-editable templates use safe variables such as `{{name}}`, `{{job_title}}`, `{{company_name}}`, `{{action_url}}`.
- Template rendering must validate required variables before sending.
- Every notification respects user preferences and mandatory/legal exceptions.

---

## 9. Frontend Public Variables

```bash
NEXT_PUBLIC_APP_URL=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_DEFAULT_LOCALE=vi
NEXT_PUBLIC_SUPPORTED_LOCALES=vi,en
NEXT_PUBLIC_BROWSER_LOCALE_DETECTION=true
```

Only `NEXT_PUBLIC_*` variables may be exposed to the browser. Never expose AI provider keys or internal service secrets through frontend env vars.

---

## 10. Observability And Jobs

```bash
BACKGROUND_WORKER_MODE=inline
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
AUDIT_LOG_ENABLED=true
PII_LOG_REDACTION_ENABLED=true
AI_TRACE_TTL_DAYS=30
```

Local default:

- `BACKGROUND_WORKER_MODE=inline` is acceptable until Celery is scaffolded.
- Async boundaries must still be coded through a queue interface so Celery can replace inline mode later.
