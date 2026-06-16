## Quick Start

Backend MVP hiện ưu tiên Python 3.14, FastAPI, SQLAlchemy 2, Pydantic v2 và Celery.

```bash
make install
make init-db
make run
```

Chạy test và lint:

```bash
make test
make lint
```

Chạy local infra bằng Docker:

```bash
make compose-up
```

Nếu chạy API local nhưng dùng Postgres/Redis từ Docker:

```bash
docker compose -f deploy/compose/docker-compose.yml up -d postgres redis
DATABASE_URL="postgresql+psycopg://app:app@localhost:55432/c2_app" \
CACHE_BACKEND=redis \
REDIS_URL="redis://localhost:6379/0" \
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Lưu ý: Docker Postgres dùng host port `55432` để tránh đụng Postgres local ở `5432`.

LLM fallback chain:

```bash
LLM_PROVIDER_CHAIN=openai,gemini,local,offline
EMBEDDING_PROVIDER_CHAIN=openai,local,offline
OPENAI_API_KEY=...
GEMINI_API_KEY=...
GEMINI_API_STYLE=native
LOCAL_BASE_URL=http://localhost:11434/v1
```

Gemini mặc định dùng native API của Google (`generateContent`, `embedContent`). Nếu cần
đi qua endpoint OpenAI-compatible của Gemini thì đổi `GEMINI_API_STYLE=openai_compatible`.
Ollama/local đang dùng OpenAI-compatible endpoint tại `LOCAL_BASE_URL`.

API docs:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Scalar API Reference: `http://127.0.0.1:8000/scalar`

Kiến trúc hiện có adapter cho OpenAI-compatible LLM, Gemini native API, local/Ollama,
offline fallback, Redis/memory cache, local/S3-compatible storage, memory/OpenSearch search,
exception handlers, rate limit middleware, RBAC dependency, webhook HMAC, RAG chunking và
prompt-injection guardrail. Production vẫn nên chạy Alembic migration rõ ràng, PgBouncer trước
Postgres, Cloudflare/Kong ở edge, và cấu hình observability tập trung.

backend/
├── alembic/                            # Lịch sử thay đổi Database (Migration)
│   ├── versions/                       # Các script SQL tự động sinh ra
│   └── env.py
│
├── app/                                # THƯ MỤC SOURCE CODE CHÍNH
│   │
│   ├── api/                            # 1. TẦNG GIAO TIẾP (INTERFACE LAYER)
│   │   ├── middlewares/                # Cửa ngõ chặn request (Auth, TraceID, RateLimit)
│   │   ├── dependencies/               # Injection (Tiêm DB session, Tiêm Quyền RBAC)
│   │   ├── exceptions/                 # Bắt lỗi toàn cục (Custom Exception Handlers)
│   │   ├── websockets/                 # Quản lý kết nối Socket.io / WebSockets realtime
│   │   ├── v1/                         # Các endpoint API v1
│   │   │   ├── routers/                # Chứa file điều hướng (auth.py, jobs.py, cvs.py...)
│   │   │   └── webhooks.py             # Endpoint nhận dữ liệu từ các hệ thống khác
│   │   └── router.py                   # File gom toàn bộ router v1
│   │
│   ├── core/                           # 2. TẦNG CỐT LÕI (SYSTEM CORE)
│   │   ├── config.py                   # Load biến môi trường (Pydantic BaseSettings)
│   │   ├── constants.py                # Hằng số toàn cục (MAX_UPLOAD_SIZE, DATE_FORMAT)
│   │   ├── security.py                 # Mã hóa JWT, Hash Bcrypt, AES Decrypt
│   │   ├── context.py                  # Asyncio Context (Lưu X-Org-Id của user đang request)
│   │   └── lifespan.py                 # Quản lý sự kiện Startup/Shutdown của Server
│   │
│   ├── domain/                         # 3. TẦNG THỰC THỂ NGUYÊN BẢN (DOMAIN LAYER)
│   │   ├── enums.py                    # Khai báo Enum (OrgType, JobStatus, RoleType)
│   │   ├── entities/                   # (Tùy chọn) Khai báo Object nghiệp vụ thuần túy
│   │   └── events/                     # Khai báo Event Schema (JobSubmitted, UserCreated)
│   │
│   ├── schemas/                        # 4. TẦNG KHUÔN MẪU DỮ LIỆU (PYDANTIC SCHEMAS)
│   │   ├── requests/                   # Validate dữ liệu Input (Ví dụ: JobCreateRequest)
│   │   ├── responses/                  # Ép kiểu dữ liệu Output (Ví dụ: JobDetailResponse)
│   │   └── dtos/                       # Data Transfer Objects (Dùng để luân chuyển giữa các Service)
│   │
│   ├── infrastructure/                 # 5. TẦNG HẠ TẦNG & GIAO TIẾP NGOÀI (INFRASTRUCTURE)
│   │   ├── database/                   # Postgres + pgvector
│   │   │   ├── session.py              # Cấu hình Pool kết nối DB
│   │   │   └── models/                 # SQLAlchemy Models (35+ bảng DBML nằm ở đây)
│   │   ├── cache/                      # Redis Client
│   │   ├── search/                     # Elasticsearch / ClickHouse Client
│   │   ├── storage/                    # Cloudflare R2 / AWS S3 Client
│   │   └── llm_gateway/                # LiteLLM Proxy / Gemini Client
│   │
│   ├── services/                       # 6. TẦNG NGHIỆP VỤ KINH DOANH (BUSINESS LOGIC)
│   │   ├── auth_service.py             # Xử lý Login, Cấp token
│   │   ├── job_service.py              # Logic đăng Job, trừ tiền Token
│   │   ├── cv_service.py               # Logic lưu CV, chuyển đổi trạng thái Masking
│   │   └── matching_service.py         # Gọi thuật toán tính điểm Vector vs Keyword
│   │
│   ├── queue/                          # 7. TẦNG QUẢN LÝ HÀNG ĐỢI & MESSAGE BROKER
│   │   ├── celery_app.py               # Khởi tạo và cấu hình App Celery
│   │   ├── kafka_client.py             # Cấu hình Producer/Consumer của Apache Kafka
│   │   └── routing.py                  # Điều hướng Task (Task AI chạy GPU, Task gửi Mail chạy CPU)
│   │
│   ├── workers/                        # 8. TẦNG THỰC THI CHẠY NGẦM (BACKGROUND WORKERS)
│   │   ├── tasks/                      # Các hàm Task thực tế (được @celery.task bọc lại)
│   │   │   ├── ai_tasks.py             # Gọi LangGraph bóc tách CV, Mock Interview
│   │   │   ├── email_tasks.py          # Xử lý gửi mail thông báo
│   │   │   └── data_sync_tasks.py      # Sync dữ liệu từ Postgres sang Elasticsearch
│   │   └── consumers/                  # Lắng nghe liên tục từ Kafka (Daemon)
│   │       └── event_listeners.py
│   │
│   ├── ai_engines/                     # 9. TẦNG TRÍ TUỆ NHÂN TẠO (AI CORE)
│   │   ├── prompts/                    # Tách riêng Prompt ra file (.txt, .yaml)
│   │   ├── guardrails/                 # NeMo Guardrails cấu hình an toàn AI
│   │   ├── rag/                        # Chunking text, Vector Retrieval
│   │   └── agents/                     # LangGraph State & Node logic
│   │
│   └── utils/                          # 10. TẦNG TIỆN ÍCH DÙNG CHUNG (UTILITIES)
│       ├── datetime_utils.py           # Format thời gian, xử lý Timezone
│       ├── file_validators.py          # Quét virus, check định dạng PDF/Word
│       ├── string_helpers.py           # Xóa dấu tiếng Việt, tạo Slug
│       └── pdf_parsers.py              # Thư viện PyMuPDF đọc text cơ bản
│
├── deploy/                             # TÀI NGUYÊN TRIỂN KHAI VẬN HÀNH
│   ├── docker/
│   │   ├── api.Dockerfile              # File build chạy API (FastAPI)
│   │   └── worker.Dockerfile           # File build chạy Background (Celery/Kafka)
│   ├── compose/
│   │   └── docker-compose.yml          # Khởi chạy Local (Postgres, Redis, Kafka...)
│   └── k8s/                            # Manifest triển khai lên Kubernetes
│
├── scripts/                            # CÁC LỆNH TIỆN ÍCH DÒNG LỆNH (CLI)
│   ├── start_api.sh                    # Script chạy Uvicorn/Gunicorn
│   ├── start_worker.sh                 # Script chạy Celery worker
│   └── init_db.py                      # Đổ dữ liệu mẫu (Kỹ năng, Tài khoản Admin)
│
├── tests/                              # TẦNG KIỂM THỬ (PYTEST)
│   ├── conftest.py                     # Khởi tạo Test DB, Mock Data
│   ├── unit/                           # Test hàm Utils, Test AI Prompts
│   ├── integration/                    # Test Services gọi Database
│   └── e2e/                            # Test API endpoints
│
├── .env.example                        # Chứa mẫu các key cần thiết
├── alembic.ini                         # Cấu hình đường dẫn cho Alembic
├── Makefile                            # Các lệnh gõ tắt (make install, make run...)
└── pyproject.toml                      # Quản lý thư viện Python (Poetry/UV)
