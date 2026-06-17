# API Contract

Canonical backend endpoints are served under `/api/v1`. The root-level endpoints in `app/api/compat.py` remain a temporary React compatibility layer.

## JD Parsing

### `POST /api/v1/jobs/parse/raw`

Request:

```json
{
  "raw_text": "Frontend Intern. Required skills: JavaScript, React.",
  "job_id": "optional-client-id",
  "company_id": "company_demo"
}
```

Response: `JobParseResponse`

```json
{
  "job_id": "job-123",
  "company_id": "company_demo",
  "title": "Frontend Intern",
  "status": "draft",
  "employment_type": "Internship",
  "location": "Hybrid",
  "salary_range": "Competitive",
  "benefits": ["Mentorship"],
  "skills": {
    "react": { "required_level": 7.0, "importance": 1.0, "required": true }
  },
  "raw_text": "Frontend Intern. Required skills: JavaScript, React.",
  "metadata": {
    "source": "raw_text",
    "jd_text_excerpt": "Frontend Intern...",
    "parser_mode": "fallback",
    "llm_used": false,
    "fallback_used": true,
    "provider_chain": []
  }
}
```

### `POST /api/v1/jobs/parse/form`

Request fields: `job_id?`, `company_id?`, `title`, `employment_type?`, `location?`, `salary_range?`, `benefits[]`, `required_skills[]`, `preferred_skills[]`, `raw_notes?`.

Response: `JobParseResponse`.

### `POST /api/v1/jobs/parse/upload`

Multipart form fields: `file`, optional query fields `job_id`, `company_id`.

Response: `JobParseResponse` with `metadata.source = "upload"`.

## JD Management

### `POST /api/v1/jobs/manage`

Request:

```json
{
  "org_id": "org-id",
  "title": "Frontend Intern",
  "description": "Build React TypeScript UI and write documentation.",
  "status": "open",
  "dept_id": null,
  "parsed_requirements": {}
}
```

Response: `JobManagementView` with fields `id`, `org_id`, `dept_id`, `title`, `description`, `parsed_requirements`, `status`.

### `GET /api/v1/jobs/manage`

Query: `limit`, `offset`, optional `org_id`, optional `status=open|closed`.

Response: `JobManagementView[]`.

### `PATCH /api/v1/jobs/{job_id}/status`

Request: `{ "status": "open" }` or `{ "status": "closed" }`.

Response: `JobManagementView`.

### `DELETE /api/v1/jobs/{job_id}`

Response:

```json
{ "status": "deleted", "job_id": "job-id" }
```

## CV Parsing

### `POST /api/v1/cvs/parse/raw`

Request:

```json
{
  "raw_text": "Chi Le\nProjects with React and Python.",
  "student_id": "mock-student-frontend-001"
}
```

Response: `CVParseResponse`

```json
{
  "student_id": "mock-student-frontend-001",
  "name": "Chi Le",
  "skills": {
    "python": {
      "score": 7.3,
      "confidence": 0.82,
      "evidence": ["Detected from CV text: python"]
    }
  },
  "metadata": {
    "source": "raw_text",
    "cv_text_excerpt": "Chi Le...",
    "parser_mode": "fallback",
    "llm_used": false,
    "fallback_used": true,
    "provider_chain": []
  }
}
```

### `POST /api/v1/cvs/parse/form`

Request fields: `student_id?`, `name`, `education?`, `experience?`, `projects?`, `skills[]`, `raw_notes?`.

Response: `CVParseResponse`.

### `POST /api/v1/cvs/parse/upload`

Multipart form fields: `file`, optional query field `student_id`.

Response: `CVParseResponse` with `metadata.source = "upload"`.

## Rule-Based Matching

Matching endpoints use frontend-ready parsed JD/CV records and return scores on a 0-100 scale.

### `POST /api/v1/matching/student/jobs`

Request:

```json
{
  "student": {
    "student_id": "student-1",
    "name": "Chi Le",
    "skills": {
      "react": { "score": 8.0, "confidence": 0.8, "evidence": ["Project"] }
    },
    "metadata": {}
  },
  "jobs": [
    {
      "job_id": "job-1",
      "company_id": "company_demo",
      "title": "Frontend Intern",
      "status": "open",
      "location": "Hybrid",
      "skills": {
        "react": { "required_level": 7.0, "importance": 1.0, "required": true }
      },
      "raw_text": null,
      "metadata": {}
    }
  ],
  "config": { "mode": "balanced" }
}
```

Response: `MatchListResponse` with `audience = "student"` and sorted `results`.

### `POST /api/v1/matching/company/candidates`

Request fields: `job`, `students[]`, optional `config`.

Response: `MatchListResponse` with `audience = "company"` and sorted `results`.

### `POST /api/v1/matching/matrix`

Request fields: `jobs[]`, `students[]`, optional `config`.

Response: `MatchListResponse` with `audience = "matrix"` and sorted `results`.

## React Compatibility Layer

`frontend/src/api.ts` currently calls root-level compatibility endpoints:

- `/jobs/parse`, `/jobs/parse-upload`, `/jobs`, `/jobs/open`, `/jobs/{job_id}/open`, `/jobs/{job_id}/close`, `/jobs/{job_id}/match`
- `/students/cv/parse`, `/students/cv/parse-upload`, `/students`, `/students/{student_id}/match-jobs`, `/students/{student_id}/jobs/{job_id}/review`

These endpoints keep the current React shapes stable. They are not the canonical contract for new backend flow work.
