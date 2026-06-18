# Evaluation Evidence

Ngày thực hiện: **2026-06-18**

Môi trường đánh giá:

- Python 3.14 virtual environment tại `backend/.venv`
- FastAPI `TestClient`
- SQLite database tạm thời, tạo schema sạch và seed bằng `seed_demo_product_data`
- `ENFORCE_RBAC=true`
- `LLM_PROVIDER_CHAIN=offline`
- Không sử dụng external AI API key

Các UUID và token nhạy cảm được lược bỏ hoặc thay bằng placeholder trong evidence.

## Summary

| ID | Test case | Result |
| --- | --- | --- |
| TC-01 | Health endpoint | PASS |
| TC-02 | Student login và identity resolution | PASS |
| TC-03 | Student dashboard | PASS |
| TC-04 | Approved jobs pagination | PASS |
| TC-05 | AI offline fallback | PASS |
| TC-06 | Document upload session | PASS |
| TC-07 | RBAC blocks Student from University dashboard | PASS |
| AUTO-01 | Complete backend test suite | PASS — 38 tests |
| AUTO-02 | Frontend TypeScript check and production build | PASS |

## TC-01 — Health endpoint

Request:

```http
GET /api/v1/health
```

Expected:

- HTTP `200`
- `status=ok`

Actual:

```text
HTTP 200
```

```json
{
  "status": "ok",
  "service": "Vinuni Career Platform",
  "env": "test"
}
```

Result: **PASS**

## TC-02 — Student login and identity resolution

Request:

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "email": "student@vinuni.edu.vn",
  "password": "password123"
}
```

Expected:

- HTTP `200`
- workspace access
- một Student identity thuộc VinUniversity
- redirect path `/student`

Actual:

```text
HTTP 200
```

```json
{
  "access_scope": "workspace",
  "user": {
    "id": "<generated-uuid>",
    "email": "student@vinuni.edu.vn",
    "full_name": "Nguyễn Anh Tuấn",
    "is_active": true
  },
  "identities": [
    {
      "org_name": "VinUniversity",
      "role_name": "student",
      "portal": "student",
      "redirect_path": "/student"
    }
  ],
  "token_type": "bearer"
}
```

Result: **PASS**

## TC-03 — Student dashboard

Request:

```http
GET /api/v1/dashboard/student
Authorization: Bearer <student-access-token>
X-Identity-Id: <student-identity-id>
```

Expected:

- HTTP `200`
- response chứa `recommended_jobs`, `applications` và `upcoming_events`

Actual:

```text
HTTP 200
```

```json
{
  "recommended_jobs_count": 2,
  "applications_count": 1,
  "upcoming_events_count": 0
}
```

Result: **PASS**

## TC-04 — Approved jobs pagination

Request:

```http
GET /api/v1/jobs/page?limit=3&offset=0&status=APPROVED
Authorization: Bearer <student-access-token>
X-Identity-Id: <student-identity-id>
```

Expected:

- HTTP `200`
- pagination metadata hợp lệ
- chỉ trả approved jobs

Actual:

```text
HTTP 200
```

```json
{
  "total": 3,
  "limit": 3,
  "offset": 0,
  "titles": [
    "Data Platform Associate",
    "LLMOps Analyst Intern",
    "Backend AI Engineer Intern"
  ]
}
```

Result: **PASS**

## TC-05 — AI offline fallback

Request:

```http
POST /api/v1/ai/chat
Authorization: Bearer <student-access-token>
X-Identity-Id: <student-identity-id>
Content-Type: application/json
```

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Summarize FastAPI for a student."
    }
  ]
}
```

Expected:

- HTTP `200`
- khi không có external API key, gateway dùng deterministic offline provider
- response vẫn có model và token accounting

Actual:

```text
HTTP 200
```

```json
{
  "provider": "offline",
  "model": "offline-deterministic",
  "content": "Offline fallback response. Configure OPENROUTER_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY to enable a real model. Input summary: Summarize FastAPI for a student.",
  "input_tokens": 8,
  "output_tokens": 41
}
```

Result: **PASS**

## TC-06 — Document upload session

Request:

```http
POST /api/v1/documents/upload-session
Authorization: Bearer <student-access-token>
X-Identity-Id: <student-identity-id>
Content-Type: application/json
```

```json
{
  "category": "cv",
  "file_name": "resume.pdf",
  "content_type": "application/pdf",
  "size_bytes": 4096
}
```

Expected:

- HTTP `201`
- generated document ID
- direct upload method `PUT`
- signed/local upload URL hết hạn sau 900 giây

Actual:

```text
HTTP 201
```

```json
{
  "document_id": "<generated-uuid>",
  "upload_method": "PUT",
  "expires_in_seconds": 900,
  "upload_url_scheme": "http"
}
```

Result: **PASS**

## TC-07 — RBAC denial across portals

Request Student identity truy cập University dashboard:

```http
GET /api/v1/dashboard/university
Authorization: Bearer <student-access-token>
X-Identity-Id: <student-identity-id>
```

Expected:

- HTTP `403`
- không rò rỉ University dashboard data

Actual:

```text
HTTP 403
```

```json
{
  "error": {
    "code": "forbidden",
    "message": "No university identity for current user",
    "trace_id": "<generated-trace-id>"
  }
}
```

Result: **PASS**

## Automated verification

### AUTO-01 — Backend complete suite

Command:

```bash
cd backend
.venv/bin/python -m pytest -q
```

Actual output:

```text
......................................                                   [100%]
38 passed
```

Pytest đồng thời phát một deprecation warning từ dependency FastAPI/Starlette TestClient; warning không làm test fail.

Result: **PASS**

### AUTO-02 — Frontend TypeScript and production build

Command:

```bash
cd frontend
pnpm check-types
pnpm build
```

Actual result:

```text
TypeScript check completed successfully.
Next.js compiled successfully and generated 26 static/dynamic routes.
```

Result: **PASS**

## Reproduction

Chạy toàn bộ backend evidence:

```bash
cd backend
.venv/bin/python -m pytest -q
```

Chạy riêng các E2E flows được dùng làm manual evidence:

```bash
cd backend
.venv/bin/python -m pytest \
  tests/e2e/test_core_flow.py \
  tests/e2e/test_documents_and_ai_runs.py \
  tests/e2e/test_registration_workflow.py \
  -q
```

Kết quả ghi nhận:

```text
..............                                                           [100%]
14 passed
```
