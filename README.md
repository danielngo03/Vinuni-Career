# VinUni Career Platform

Nền tảng nghề nghiệp B2B2C hợp nhất dành cho ba nhóm người dùng:

- **Student**: quản lý hồ sơ/CV, tìm việc, ứng tuyển, theo dõi phỏng vấn, sự kiện và AI career coaching.
- **Partner**: đăng tin tuyển dụng, quản lý ứng viên, lịch phỏng vấn và quy trình tuyển dụng.
- **University**: duyệt đăng ký, kiểm duyệt nội dung, quản trị taxonomy, dashboard và governance.

Repository gồm một frontend Next.js và một backend FastAPI modular monolith. Backend hỗ trợ RBAC theo organization/identity, document lifecycle, outbox/worker, AI gateway nhiều provider, AI runs bất đồng bộ và Server-Sent Events.

## Submission links

| Hạng mục | Liên kết |
| --- | --- |
| MVP demo video (~3 phút) | **TODO:** Thay URL này bằng YouTube link trước khi nộp: `https://youtu.be/REPLACE_WITH_DEMO_VIDEO` |
| Architecture diagram | [Architecture](#architecture-diagram) |
| Setup instructions | [Local setup](#local-setup) |
| Environment variables | [Environment variables](#environment-variables) |
| Sample API queries | [Sample API queries](#sample-api-queries) |
| Evaluation evidence | [`eval/README.md`](eval/README.md) |
| Backend API reference | `http://127.0.0.1:8000/scalar` sau khi chạy backend |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |

> FastAPI Swagger UI tại `/docs` đang được tắt có chủ đích. Dự án sử dụng Scalar tại `/scalar`.

## Main capabilities

| Capability | Student | Partner | University |
| --- | :---: | :---: | :---: |
| Password login, refresh-token rotation, logout | ✓ | ✓ | ✓ |
| Google/Microsoft OIDC khi được cấu hình | ✓ | ✓ | ✓ |
| Organization-scoped identity và RBAC | ✓ | ✓ | ✓ |
| Registration + university approval workflow | ✓ | ✓ | Reviewer |
| Role-specific dashboard | ✓ | ✓ | ✓ |
| Job search, details và bookmark | ✓ |  |  |
| CV upload, inspection, masking và AI extraction | ✓ |  |  |
| Job posting và candidate pipeline |  | ✓ | Moderate |
| Applications, consent và interviews | ✓ | ✓ |  |
| Events và registration | ✓ | ✓ | ✓ |
| Notifications và company reviews | ✓ | ✓ | ✓ |
| AI chat, embedding, rerank và matching | ✓ | ✓ | ✓ |
| Asynchronous specialist AI runs + SSE | ✓ | ✓ | ✓ |
| Document scan lifecycle | ✓ | ✓ | ✓ |
| Workflow, webhook và global search | ✓ | ✓ | ✓ |

## Technology stack

### Frontend

- Next.js `16.2.9`, App Router và React `19.2.4`
- TypeScript `5.9`, Tailwind CSS 4, Radix UI và Phosphor Icons
- Một deployment phục vụ landing page và ba workspace theo hostname
- BFF routes lưu access/refresh token trong cookie `HttpOnly`
- OpenAPI-generated TypeScript schema tại `frontend/src/lib/api/schema.d.ts`
- Giao diện đa ngôn ngữ Việt/Anh

### Backend

- Python `3.12+`, FastAPI, Pydantic 2 và SQLAlchemy 2
- Alembic migrations; PostgreSQL cho môi trường triển khai, SQLite dùng được cho demo/test local
- JWT access token, rotating refresh token, identity context và RBAC
- Redis/Celery adapter cho distributed workers; local in-process workflow cho development
- Local/S3 storage adapter; memory/Redis cache; memory/Elasticsearch/OpenSearch search adapter
- OpenAI, Gemini, Groq, OpenRouter, NVIDIA và deterministic offline AI provider
- Pytest, Ruff, Mypy, architecture tests, contract tests và E2E tests

## Repository structure

```text
C2-App-037/
├── backend/
│   ├── app/
│   │   ├── bootstrap/          # FastAPI factory, middleware, routes, lifespan
│   │   ├── shared/             # Config, security, errors, events, IDs
│   │   ├── modules/            # Business capabilities
│   │   │   ├── access/
│   │   │   ├── registrations/
│   │   │   ├── institution/
│   │   │   ├── students/
│   │   │   ├── opportunities/
│   │   │   ├── recruitment/
│   │   │   ├── documents/
│   │   │   ├── engagement/
│   │   │   ├── reporting/
│   │   │   ├── automation/
│   │   │   └── ai_operations/
│   │   ├── ai/                 # Agents, gateway, safety, extraction, retrieval
│   │   └── platform/           # DB, cache, storage, search, workflows
│   ├── alembic/                # Database migrations
│   ├── contracts/              # Exported OpenAPI contract
│   ├── scripts/                # Seed DB, API/worker startup, AI smoke test
│   └── tests/                  # Unit, architecture, contract và E2E
├── frontend/
│   ├── src/app/                # Next.js pages và BFF route handlers
│   ├── src/features/           # Product features theo domain
│   ├── src/components/         # Shared UI/layout components
│   ├── src/lib/                # API, auth, i18n và utilities
│   └── public/                 # Brand và image assets
├── eval/                       # Manual evaluation evidence
├── scripts/                    # AI usage logging hooks của khóa học
├── Makefile                    # Root developer commands
└── README.md
```

Backend tuân theo modular-monolith bốn lớp. Mỗi business module hướng tới cấu trúc:

```text
module/
├── api/                        # HTTP contracts và route handlers
├── application/                # Use cases, commands, queries, ports
├── domain/                     # Business rules, không phụ thuộc framework
└── infrastructure/             # SQLAlchemy repositories/adapters
```

## Architecture diagram

### Component architecture

```mermaid
flowchart TB
    subgraph Clients["Client layer"]
        Browser["Web browser"]
        Student["Student"]
        Partner["Partner / HR"]
        University["University / Career Center"]
        Student --> Browser
        Partner --> Browser
        University --> Browser
    end

    subgraph Frontend["Next.js 16 frontend :3000"]
        Router["App Router + locale routing"]
        Workspaces["Student / Partner / University workspaces"]
        AuthBFF["Auth BFF<br/>/api/auth/*"]
        APIBFF["Authenticated API proxy<br/>/api/backend/*"]
        Cookies["HttpOnly cookies<br/>access + refresh + identity + portal"]

        Router --> Workspaces
        Workspaces --> AuthBFF
        Workspaces --> APIBFF
        AuthBFF <--> Cookies
        APIBFF <--> Cookies
    end

    subgraph Backend["FastAPI modular monolith :8000"]
        Middleware["CORS + request context + rate limiting"]
        Composition["bootstrap/routes.py<br/>single HTTP composition root"]

        subgraph Modules["Business modules"]
            Access["Access + Identity + RBAC"]
            Registration["Registration + Verification"]
            Institution["Institution taxonomy"]
            Students["Student profiles"]
            Opportunities["Jobs + Events"]
            Recruitment["CVs + Applications + Interviews"]
            Documents["Documents"]
            Engagement["Reviews + Notifications"]
            Reporting["Role dashboards"]
            Automation["Workflows + Webhooks"]
            AIOps["AI run lifecycle + SSE"]
            SearchAPI["Global search API"]
        end

        Middleware --> Composition
        Composition --> Access
        Composition --> Registration
        Composition --> Institution
        Composition --> Students
        Composition --> Opportunities
        Composition --> Recruitment
        Composition --> Documents
        Composition --> Engagement
        Composition --> Reporting
        Composition --> Automation
        Composition --> AIOps
        Composition --> SearchAPI
    end

    subgraph AISubsystem["Provider-independent AI subsystem"]
        Safety["PII masking + prompt-injection guard"]
        Extraction["OCR / structured extraction"]
        Retrieval["Chunking + embeddings + hybrid retrieval + rerank"]
        Agents["Specialist workforce + bounded ReAct runtime"]
        Gateway["LLM gateway<br/>routing + retry + circuit breaker"]
        Providers["NVIDIA / OpenRouter / OpenAI / Gemini / Offline"]

        Agents --> Safety
        Agents --> Extraction
        Agents --> Retrieval
        Safety --> Gateway
        Extraction --> Gateway
        Retrieval --> Gateway
        Gateway --> Providers
    end

    subgraph Platform["Platform adapters"]
        SQL["SQLAlchemy + Alembic"]
        DB[("PostgreSQL<br/>or SQLite local")]
        Outbox[("Outbox events")]
        Cache["Memory / Redis cache"]
        Search["Memory / OpenSearch / Elasticsearch"]
        Storage["Local filesystem / S3"]
        Workflow["Local dispatcher / Celery / Temporal port"]
        Workers["AI / document / notification workers"]

        SQL --> DB
        SQL --> Outbox
        Workflow --> Workers
        Workers --> Outbox
    end

    subgraph External["External services"]
        OIDC["Google / Microsoft OIDC"]
        ObjectStore["S3-compatible object storage"]
        Redis["Redis broker/cache"]
        ModelAPIs["External model APIs"]
    end

    Browser --> Frontend
    AuthBFF -->|"JSON over HTTP"| Middleware
    APIBFF -->|"Bearer token + X-Identity-Id"| Middleware
    Access <--> OIDC
    Modules --> SQL
    Modules --> Cache
    Modules --> Search
    Documents --> Storage
    Automation --> Workflow
    AIOps --> Workflow
    AIOps --> AISubsystem
    Recruitment --> AISubsystem
    Opportunities --> AISubsystem
    Storage -. production .-> ObjectStore
    Cache -. optional .-> Redis
    Workflow -. Celery .-> Redis
    Providers --> ModelAPIs
```

### End-to-end data flow

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant W as Next.js workspace
    participant B as Next.js BFF
    participant API as FastAPI
    participant AUTH as Access/RBAC
    participant MOD as Business module
    participant DB as Database/Outbox
    participant WF as Workflow/Worker
    participant AI as AI subsystem/provider

    U->>W: Login bằng email/password
    W->>B: POST /api/auth/login
    B->>API: POST /api/v1/auth/login
    API->>AUTH: Verify password, create access/refresh session
    AUTH->>DB: Persist refresh-token family/session
    API-->>B: Tokens + available identities
    B-->>W: Set HttpOnly cookies, return non-secret profile

    U->>W: Chọn identity và thực hiện nghiệp vụ
    W->>B: Request /api/backend/*
    B->>API: Bearer token + X-Identity-Id
    API->>AUTH: Authenticate + resolve organization + authorize permission
    AUTH-->>API: Current user and active identity
    API->>MOD: Execute application use case
    MOD->>DB: Transactional read/write + outbox event
    DB-->>MOD: Persisted result

    opt Long-running document or AI operation
        MOD->>WF: Dispatch job/run ID
        WF->>AI: Safety, extraction, retrieval or specialist agent
        AI-->>WF: Structured result and progress events
        WF->>DB: Update run/document state
        W->>B: Poll status or open SSE stream
        B->>API: GET /ai/runs/{id} or /stream
        API-->>W: Progress/result
    end

    MOD-->>API: Response DTO
    API-->>B: JSON response
    B-->>W: Forward response, rotate token after eligible 401
    W-->>U: Update role-specific UI
```

### Important data-flow rules

1. Browser không đọc trực tiếp access/refresh token; token nằm trong cookie `HttpOnly`.
2. BFF thêm `Authorization: Bearer ...` và `X-Identity-Id` khi gọi FastAPI.
3. Backend luôn resolve active identity để ràng buộc user với organization và role.
4. Business modules ghi dữ liệu qua SQLAlchemy; các sự kiện nền được ghi vào outbox.
5. AI operations trả `run_id` với HTTP `202`, sau đó client poll hoặc nhận tiến trình qua SSE.
6. AI gateway chọn provider theo chain, áp dụng timeout/retry/circuit breaker và có offline fallback.
7. Tài liệu chỉ được download sau khi qua document ownership/ACL và trạng thái scan phù hợp.

## Local setup

### Prerequisites

- macOS, Linux hoặc WSL khuyến nghị.
- Python `3.12.x` hoặc mới hơn vì `backend/pyproject.toml` yêu cầu `>=3.12,<3.15`.
- Node.js `20+`.
- pnpm `10.19.x`; có thể kích hoạt bằng Corepack.
- Git.
- PostgreSQL nếu dùng cấu hình database mặc định. SQLite có thể dùng cho demo nhanh.
- Redis chỉ bắt buộc khi dùng Redis cache hoặc Celery worker. Luồng local mặc định dùng memory adapters và `WORKFLOW_BACKEND=local`.

```bash
python3 --version
node --version
corepack enable
pnpm --version
```

### 1. Enter the project

```bash
cd Build/C2-App-037
```

### 2. Create local environment files

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

Root `.env` chỉ phục vụ AI logging hooks của khóa học. Nếu cần:

```bash
cp .env.example .env
```

Không commit API key, database password hoặc production secret vào Git.

### 3. Select a database

#### Option A — SQLite for the fastest local demo

Đổi dòng sau trong `backend/.env`:

```dotenv
DATABASE_URL=sqlite:///./vinuni_career.db
```

Option này không cần cài PostgreSQL và phù hợp để chạy MVP demo, seed data và test API.

#### Option B — PostgreSQL

Tạo database và giữ URL mặc định, hoặc thay bằng thông tin của máy:

```dotenv
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/vinuni_career
```

Ví dụ bằng PostgreSQL CLI:

```bash
createuser --createdb app
createdb --owner=app vinuni_career
psql -c "ALTER USER app WITH PASSWORD 'app';"
```

### 4. Install dependencies, migrate and seed

```bash
make install-local
```

Lệnh trên:

1. tạo `backend/.venv`;
2. cài backend cùng development dependencies;
3. chạy Alembic migrations;
4. seed demo organizations, users, jobs, CV, application và events;
5. cài frontend dependencies bằng pnpm.

Nếu đã cài dependency và chỉ muốn reset/seed schema:

```bash
make backend-init-db
```

### 5. Run the application

Chạy backend/frontend ở foreground:

```bash
make dev-foreground
```

Hoặc chạy background:

```bash
make dev-all
make dev-logs
make dev-down
```

Local URLs:

| Service | URL |
| --- | --- |
| Frontend | <http://localhost:3000> |
| Vietnamese landing page | <http://localhost:3000/vi> |
| English landing page | <http://localhost:3000/en> |
| FastAPI health | <http://127.0.0.1:8000/api/v1/health> |
| Scalar API reference | <http://127.0.0.1:8000/scalar> |
| OpenAPI JSON | <http://127.0.0.1:8000/openapi.json> |

Có thể chạy riêng từng service:

```bash
make backend-api
make frontend-dev
```

### Demo accounts

| Portal | Email | Password | Local route |
| --- | --- | --- | --- |
| Student | `student@vinuni.edu.vn` | `password123` | `/vi/student` |
| Partner | `hr@partner.vn` | `password123` | `/vi/partner` |
| University | `career.center@vinuni.edu.vn` | `password123` | `/vi/university` |

Ngoài local development, frontend hỗ trợ hostname routing:

- `example.com`: landing/login
- `student.example.com`: Student workspace
- `partner.example.com`: Partner workspace
- `uni.example.com`: University workspace

`NEXT_PUBLIC_APP_DOMAIN` điều khiển base domain; local development vẫn dùng một server tại port `3000`.

## Environment variables

Nguồn cấu hình runtime:

- Backend: `backend/.env`, được đọc bởi `backend/app/shared/config.py`.
- Frontend: `frontend/.env.local`.
- AI logging hooks: root `.env`.

### Backend — application, security and database

| Variable | Required | Default/example | Purpose |
| --- | --- | --- | --- |
| `APP_NAME` | No | `Vinuni Career Platform` | Service name |
| `APP_ENV` | No | `local` | `local`, `test`, `staging`, `production` |
| `API_V1_PREFIX` | No | `/api/v1` | API prefix |
| `DEBUG` | No | `false` | Debug mode |
| `LOG_LEVEL` | No | `INFO` | Application log level |
| `SECRET_KEY` | **Yes outside test** | no safe production default | JWT signing secret, tối thiểu 32 ký tự |
| `ALGORITHM` | No | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Access-token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `14` | Refresh-token TTL |
| `ENFORCE_RBAC` | No | `true` | Enforce permission checks |
| `RATE_LIMIT_ENABLED` | No | `true` | Enable API rate limiting |
| `RATE_LIMIT_REQUESTS` | No | `120` | Requests per rate-limit window |
| `RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Rate-limit window |
| `DATABASE_URL` | **Yes** | PostgreSQL URL | SQLAlchemy database connection |
| `BACKEND_CORS_ORIGINS` | No | `["http://localhost:3000"]` | JSON array hoặc comma-separated origins |
| `INTERNAL_SERVICE_TOKEN` | Required for scan callback | empty | Authenticates internal document scan callback |
| `WEBHOOK_SHARED_SECRET` | Required for signed webhooks | empty | Verifies inbound webhook signatures |
| `MAX_UPLOAD_MB` | No | `20` | Maximum upload size |
| `SIGNED_URL_TTL_SECONDS` | No | `900` | Signed storage URL lifetime |
| `SCALAR_DOCS_ENABLED` | No | `true` | Enable Scalar API reference |
| `SCALAR_DOCS_PATH` | No | `/scalar` | Scalar route |

### Backend — workflow, cache, search and storage

| Variable | Required | Default/example | Purpose |
| --- | --- | --- | --- |
| `REDIS_URL` | When Redis cache is selected | `redis://localhost:6379/0` | Redis cache connection |
| `CELERY_BROKER_URL` | When Celery is selected | `redis://localhost:6379/1` | Celery broker |
| `CELERY_RESULT_BACKEND` | When Celery is selected | `redis://localhost:6379/2` | Celery result backend |
| `WORKFLOW_BACKEND` | No | `local` | `local`, `celery`, or `temporal` |
| `TEMPORAL_ADDRESS` | For Temporal | `localhost:7233` | Temporal server |
| `TEMPORAL_NAMESPACE` | For Temporal | `default` | Temporal namespace |
| `TEMPORAL_TASK_QUEUE` | For Temporal | `vinuni-career` | Temporal task queue |
| `CACHE_BACKEND` | No | `memory` | `memory` or `redis` |
| `CACHE_DEFAULT_TTL_SECONDS` | No | `300` | Cache TTL |
| `SEARCH_BACKEND` | No | `memory` | `memory`, `opensearch`, `elasticsearch` |
| `SEARCH_URL` | For external search | empty | Search cluster URL |
| `SEARCH_INDEX_PREFIX` | No | `vinuni` | Search index prefix |
| `SEARCH_API_KEY` | Optional | empty | Search API key |
| `SEARCH_USERNAME` | Optional | empty | Search basic-auth username |
| `SEARCH_PASSWORD` | Optional | empty | Search basic-auth password |
| `STORAGE_BACKEND` | No | `local` | `local` or `s3` |
| `STORAGE_LOCAL_ROOT` | For local storage | `./.data/uploads` | Local object root |
| `STORAGE_PUBLIC_BASE_URL` | For local storage | `http://localhost:8000/files` | Base URL returned for local files |
| `S3_ENDPOINT_URL` | For S3-compatible storage | empty | S3 endpoint |
| `S3_BUCKET` | For S3 | empty | Bucket name |
| `S3_ACCESS_KEY_ID` | For S3 | empty | Access key |
| `S3_SECRET_ACCESS_KEY` | For S3 | empty | Secret key |

### Backend — AI gateway and providers

Ít nhất một real provider key là cần thiết nếu muốn gọi model thật. Nếu không có key hoặc provider lỗi, chain có thể rơi về `offline`.

| Variable | Required | Default/example | Purpose |
| --- | --- | --- | --- |
| `LLM_PROVIDER` | No | `nvidia` | Preferred chat provider |
| `LLM_PROVIDER_CHAIN` | No | `nvidia,openrouter,offline` | Ordered provider fallback chain |
| `LLM_MODEL` | No | provider model name | Default model |
| `LLM_TIMEOUT_SECONDS` | No | `12` in example | Provider timeout |
| `LLM_MAX_RETRIES` | No | `1` in example | Maximum retries |
| `LLM_RETRY_BACKOFF_SECONDS` | No | `0.35` | Retry backoff |
| `EMBEDDING_PROVIDER_CHAIN` | No | `nvidia,openrouter,offline` | Embedding fallback chain |
| `AI_DAILY_ORG_TOKEN_LIMIT` | No | `200000` | Daily organization token budget |
| `AI_GATEWAY_MODE` | No | `direct` | `direct` or `litellm_proxy` |
| `LITELLM_PROXY_URL` | For LiteLLM proxy | empty | Proxy URL |
| `LITELLM_API_KEY` | For protected LiteLLM | empty | Proxy credential |
| `OPENAI_API_KEY` | For OpenAI | empty | OpenAI credential |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | OpenAI-compatible URL |
| `OPENAI_MODEL` | No | configured model | Chat model |
| `OPENAI_EMBEDDING_MODEL` | No | `text-embedding-3-small` | Embedding model |
| `GEMINI_API_KEY` | For Gemini | empty | Gemini credential |
| `GEMINI_API_STYLE` | No | `native` | `native` or `openai_compatible` |
| `GEMINI_BASE_URL` | No | Google Generative Language API | Native API base |
| `GEMINI_OPENAI_BASE_URL` | No | Gemini OpenAI-compatible API | Compatible API base |
| `GEMINI_MODEL` | No | configured model | Chat/vision model |
| `GEMINI_EMBEDDING_MODEL` | No | configured model | Embedding model |
| `GROQ_API_KEY` | For Groq | empty | Groq credential |
| `GROQ_BASE_URL` | No | `https://api.groq.com/openai/v1` | Groq OpenAI-compatible API base |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Chat model |
| `GROQ_EMBEDDING_MODEL` | No | empty | Optional OpenAI-compatible embedding model |
| `OPENROUTER_API_KEY` | For OpenRouter | empty | OpenRouter credential |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | API base |
| `OPENROUTER_HTTP_REFERER` | Recommended | `http://localhost:3000` | OpenRouter application referer |
| `OPENROUTER_APP_TITLE` | Recommended | app name | OpenRouter application title |
| `OPENROUTER_MODEL` | No | configured model | Primary model |
| `OPENROUTER_MODEL_FALLBACKS` | No | comma-separated models | Model fallback list |
| `OPENROUTER_SAFETY_MODEL` | No | configured model | Moderation/safety model |
| `OPENROUTER_EMBEDDING_MODEL` | No | configured model | Embedding model |
| `OPENROUTER_RERANK_MODEL` | No | configured model | Rerank model |
| `NVIDIA_API_KEY` | For NVIDIA NIM | empty | NVIDIA credential |
| `NVIDIA_BASE_URL` | No | `https://integrate.api.nvidia.com/v1` | NVIDIA API base |
| `NVIDIA_MODEL` | No | configured model | Chat model |
| `NVIDIA_EMBEDDING_MODEL` | No | configured model | Embedding model |
| `NVIDIA_RERANK_MODEL` | No | configured model | Rerank model |
| `VISION_EXTRACTION_PROVIDER` | No | configured provider | OCR/vision provider |
| `VISION_EXTRACTION_MODEL` | No | configured model | OCR/vision model |
| `STRUCTURED_EXTRACTION_ENABLED` | No | `true` | Structured extraction |
| `MAX_EXTRACTION_RETRIES` | No | `2` | Extraction retry limit |
| `SEMANTIC_CACHE_ENABLED` | No | `true` | Semantic cache flag |
| `GUARDRAILS_ENABLED` | No | `true` | AI safety guardrails |
| `RERANK_PROVIDER` | No | `nvidia` | Rerank adapter |
| `COHERE_API_KEY` | For Cohere rerank | empty | Cohere credential |
| `LANGFUSE_ENABLED` | No | `false` | Langfuse tracing |
| `LANGFUSE_PUBLIC_KEY` | For Langfuse | empty | Public key |
| `LANGFUSE_SECRET_KEY` | For Langfuse | empty | Secret key |
| `LANGFUSE_HOST` | No | `https://cloud.langfuse.com` | Langfuse host |

### Backend — OIDC

| Variable | Required | Default/example | Purpose |
| --- | --- | --- | --- |
| `OIDC_BACKEND_CALLBACK_BASE` | For OIDC | local backend callback | Backend callback base |
| `OIDC_FRONTEND_CALLBACK_URL` | For OIDC | local frontend callback | Browser callback URL |
| `GOOGLE_OIDC_CLIENT_ID` | For Google login | empty | Google client ID |
| `GOOGLE_OIDC_CLIENT_SECRET` | For Google login | empty | Google secret |
| `GOOGLE_OIDC_DISCOVERY_URL` | No | Google discovery endpoint | OIDC discovery |
| `MICROSOFT_OIDC_CLIENT_ID` | For Microsoft login | empty | Microsoft client ID |
| `MICROSOFT_OIDC_CLIENT_SECRET` | For Microsoft login | empty | Microsoft secret |
| `MICROSOFT_OIDC_TENANT` | No | `common` | Microsoft tenant |

### Frontend

| Variable | Required | Default/example | Purpose |
| --- | --- | --- | --- |
| `BACKEND_URL` | No | `http://127.0.0.1:8000/api/v1` | Server-side FastAPI base URL |
| `NEXT_PUBLIC_APP_DOMAIN` | No | `example.com` | Production hostname routing |
| `SESSION_COOKIE_DOMAIN` | Production subdomains | empty local | Shared cookie domain, e.g. `.example.com` |
| `NEXT_PUBLIC_DEFAULT_LOCALE` | No | `vi` | Default locale |

### Course AI logging hooks

| Variable | Required | Purpose |
| --- | --- | --- |
| `AI_LOG_SERVER` | Theo yêu cầu khóa học | Log ingestion endpoint |
| `AI_LOG_API_KEY` | Theo yêu cầu khóa học | Credential do giảng viên cung cấp |
| `AI_LOG_DIR` | No | Local AI log directory |
| `LOG_LEVEL` | No | Hook logging level |

## Sample API queries

Các ví dụ dưới đây giả định backend đang chạy tại `http://127.0.0.1:8000`.

### 1. Health check

```bash
curl -s http://127.0.0.1:8000/api/v1/health | jq
```

```json
{
  "status": "ok",
  "service": "Vinuni Career Platform",
  "env": "local"
}
```

### 2. Login and select the Student identity

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "student@vinuni.edu.vn",
    "password": "password123"
  }' > /tmp/vinuni-login.json

export ACCESS_TOKEN="$(jq -r '.access_token' /tmp/vinuni-login.json)"
export IDENTITY_ID="$(jq -r '.identities[] | select(.portal == "student") | .id' /tmp/vinuni-login.json)"
```

API calls theo workspace cần cả access token và identity:

```bash
export AUTH_HEADER="Authorization: Bearer $ACCESS_TOKEN"
export IDENTITY_HEADER="X-Identity-Id: $IDENTITY_ID"
```

### 3. Fetch the Student dashboard

```bash
curl -s http://127.0.0.1:8000/api/v1/dashboard/student \
  -H "$AUTH_HEADER" \
  -H "$IDENTITY_HEADER" | jq
```

### 4. Query approved jobs with pagination

```bash
curl -s \
  'http://127.0.0.1:8000/api/v1/jobs/page?status=APPROVED&limit=10&offset=0' \
  -H "$AUTH_HEADER" \
  -H "$IDENTITY_HEADER" | jq
```

### 5. Search jobs

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/search \
  -H "$AUTH_HEADER" \
  -H "$IDENTITY_HEADER" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "FastAPI PostgreSQL",
    "entity_type": "job",
    "limit": 5
  }' | jq
```

### 6. AI chat with provider fallback

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/chat \
  -H "$AUTH_HEADER" \
  -H "$IDENTITY_HEADER" \
  -H 'Content-Type: application/json' \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Gợi ý ba bước chuẩn bị cho vị trí Backend AI Intern."
      }
    ],
    "temperature": 0.2
  }' | jq
```

Nếu không cấu hình real provider key, response hợp lệ sẽ có:

```json
{
  "provider": "offline",
  "model": "offline-deterministic"
}
```

### 7. Start an asynchronous specialist AI run

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/ai/runs/ \
  -H "$AUTH_HEADER" \
  -H "$IDENTITY_HEADER" \
  -H 'Content-Type: application/json' \
  -d '{
    "run_type": "career_coaching",
    "run_metadata": {
      "locale": "vi",
      "goal": "Backend AI internship"
    }
  }' > /tmp/vinuni-ai-run.json

export RUN_ID="$(jq -r '.run_id' /tmp/vinuni-ai-run.json)"
cat /tmp/vinuni-ai-run.json | jq
```

Poll status:

```bash
curl -s "http://127.0.0.1:8000/api/v1/ai/runs/$RUN_ID" \
  -H "$AUTH_HEADER" \
  -H "$IDENTITY_HEADER" | jq
```

Stream progress bằng SSE:

```bash
curl -N "http://127.0.0.1:8000/api/v1/ai/runs/$RUN_ID/stream" \
  -H "$AUTH_HEADER" \
  -H "$IDENTITY_HEADER"
```

### 8. Create a document upload session

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/documents/upload-session \
  -H "$AUTH_HEADER" \
  -H "$IDENTITY_HEADER" \
  -H 'Content-Type: application/json' \
  -d '{
    "category": "cv",
    "file_name": "resume.pdf",
    "content_type": "application/pdf",
    "size_bytes": 4096
  }' | jq
```

Response gồm `document_id`, `upload_url`, HTTP method `PUT` và thời gian hết hạn. Với S3, client PUT file trực tiếp vào presigned URL rồi gọi:

```bash
curl -s -X POST \
  "http://127.0.0.1:8000/api/v1/documents/$DOCUMENT_ID/complete" \
  -H "$AUTH_HEADER" \
  -H "$IDENTITY_HEADER" \
  -H 'Content-Type: application/json' \
  -d '{"checksum_sha256": "<64-character-sha256>"}' | jq
```

### 9. List discoverable AI agents

Endpoint này không yêu cầu đăng nhập:

```bash
curl -s http://127.0.0.1:8000/api/v1/ai/runs/capabilities | jq
```

Các task type hiện có gồm `cv_extraction`, `profile_matching`, `jd_analysis`, `moderation`, `admin_review`, `verification` và `career_coaching`.

## API overview

| Prefix | Responsibility |
| --- | --- |
| `/api/v1/auth` | Register, login, refresh, logout, OIDC, session và identity |
| `/api/v1/registrations` | Student/partner onboarding, pending state, review queue |
| `/api/v1/organizations` | Institution taxonomy, departments, industries |
| `/api/v1/students` | Student profiles |
| `/api/v1/jobs` | Jobs, bookmarks và applications |
| `/api/v1/events` | Events và event registration |
| `/api/v1/cvs` | CV CRUD, upload, inspection và masking |
| `/api/v1/interviews` | Interview scheduling |
| `/api/v1/dashboard` | Student, partner và university dashboards |
| `/api/v1/documents` | Upload session, scan state và signed download |
| `/api/v1/ai` | Synchronous compatibility AI APIs |
| `/api/v1/ai/runs` | Asynchronous AI run lifecycle và SSE |
| `/api/v1/notifications` | Notification inbox |
| `/api/v1/reviews` | Company reviews |
| `/api/v1/workflows` | Workflow definitions/execution |
| `/api/v1/webhooks` | Integration webhooks |
| `/api/v1/search` | Cross-entity search |

OpenAPI contract được export tại `backend/contracts/openapi-v1.json`. Regenerate:

```bash
cd backend
make contract
cd ../frontend
pnpm generate:api
```

## Verification and evaluation

### Backend

```bash
cd backend
make check
make migration-check
make ai-smoke
```

Hoặc chỉ chạy tests:

```bash
make backend-test
```

Kết quả kiểm chứng ngày **2026-06-18**:

```text
38 passed
```

Bộ test gồm unit, architecture boundaries, OpenAPI contract và E2E authorization/business flows.

### Frontend

```bash
cd frontend
pnpm lint
pnpm check-types
pnpm build
```

Kết quả kiểm chứng ngày **2026-06-18**: `pnpm check-types` và `pnpm build` đều pass.

### Manual evidence

[`eval/README.md`](eval/README.md) ghi lại 7 manual/API test cases cùng command, expected result và output thực tế:

1. health check;
2. Student login và identity;
3. Student dashboard;
4. approved-job pagination;
5. AI offline fallback;
6. document upload session;
7. RBAC denial khi Student truy cập University dashboard.

## Suggested 3-minute MVP demo flow

Kịch bản quay video đề xuất:

1. **00:00–00:20** — Mở landing page, giới thiệu ba portal.
2. **00:20–00:45** — Login bằng tài khoản Student.
3. **00:45–01:15** — Xem dashboard, recommended jobs và profile/application status.
4. **01:15–01:45** — Mở Jobs, tìm kiếm/filter và bookmark một job.
5. **01:45–02:15** — Mở CV Center, xem CV masking/document/AI capabilities.
6. **02:15–02:40** — Chạy career coaching AI operation và xem trạng thái/result.
7. **02:40–03:00** — Logout, login University và cho thấy moderation/registration governance.

Sau khi upload video, thay link tại [Submission links](#submission-links).

## Security design

- Access và refresh token được lưu trong secure-capable `HttpOnly`, `SameSite=Lax` cookies.
- Frontend BFF tự gắn Bearer token và active identity; browser components không cần đọc token.
- Refresh token được rotation; reuse của token cũ trả HTTP `401`.
- RBAC kiểm tra permission và portal/organization context.
- Rate-limit middleware hỗ trợ distributed cache.
- Document callback dùng constant-time comparison với `INTERNAL_SERVICE_TOKEN`.
- AI subsystem có PII masking, prompt-injection checks, bounded tool execution và auditable summaries.
- Sensitive provider keys chỉ thuộc server-side environment.
- Production phải thay `SECRET_KEY`, database credentials, service token và webhook secret.

## Current limitations

Đây là MVP có production-oriented architecture, nhưng các mục sau chưa nên được mô tả là production-complete:

- Temporal adapter là port/future target; local dispatcher và Celery là các đường chạy hiện tại.
- Malware scanner production và authenticated local object PUT adapter chưa hoàn thiện.
- pgvector persistence, load tests và model-evaluation release gates chưa hoàn thiện.
- Reporting hiện còn một số cross-domain reads thay vì projection tables hoàn toàn độc lập.
- Một số business ORM models vẫn đang được tách dần khỏi platform model aggregator.
- Root Makefile còn các Docker Compose targets, nhưng compose manifests không có trong working tree hiện tại; dùng setup local ở trên hoặc khôi phục deployment manifests trước khi chạy các target đó.

Chi tiết kỹ thuật: [`backend/architecture/inventory.md`](backend/architecture/inventory.md).

## Troubleshooting

### `connection refused` khi migrate

`DATABASE_URL` đang trỏ tới PostgreSQL nhưng PostgreSQL chưa chạy. Khởi động PostgreSQL hoặc chuyển sang:

```dotenv
DATABASE_URL=sqlite:///./vinuni_career.db
```

### Port 3000 hoặc 8000 đang được sử dụng

```bash
make dev-down
lsof -i :3000
lsof -i :8000
```

### AI luôn trả provider `offline`

Đây là fallback có chủ đích. Cấu hình ít nhất một provider key và đảm bảo provider nằm trong `LLM_PROVIDER_CHAIN`.

### API trả `401 Not authenticated`

Đăng nhập lại hoặc gửi `Authorization: Bearer <token>`. Khi đi qua frontend, dùng `/api/backend/*` để BFF tự gắn token.

### API trả lỗi identity hoặc `403`

Các endpoint theo workspace cần header:

```text
X-Identity-Id: <identity id returned by login>
```

Identity phải thuộc user hiện tại và đúng portal/organization được endpoint yêu cầu.

### `/docs` trả `404`

Swagger UI được tắt. Dùng:

```text
http://127.0.0.1:8000/scalar
```

## License and submission note

Đây là dự án học tập thuộc AI20K Build Cohort 2. Trước khi nộp:

- thay TODO YouTube URL;
- không commit secret thật;
- chạy lại backend tests và frontend checks;
- cập nhật evidence nếu output thay đổi;
- bảo đảm demo account và seed data vẫn hoạt động.
