# VinUni Career Platform

Nền tảng nghề nghiệp B2B2C có tích hợp AI dành cho sinh viên, nhà tuyển dụng và
đội ngũ career center của trường đại học.

Demo production: https://c2-app-037-production.up.railway.app/vi

## Dự án này là gì?

VinUni Career Platform gom ba nhóm quy trình nghề nghiệp vào một sản phẩm:

- Sinh viên quản lý hồ sơ và CV, tìm việc và sự kiện, ứng tuyển, theo dõi phỏng
  vấn, và dùng AI để hỗ trợ định hướng nghề nghiệp.
- Đối tác đăng cơ hội tuyển dụng, quản lý ứng viên, xem hồ sơ ứng tuyển và điều
  phối phỏng vấn.
- Nhà trường duyệt đăng ký, kiểm duyệt nội dung, quản lý taxonomy, theo dõi hoạt
  động và vận hành nền tảng.

Repository gồm frontend Next.js và backend FastAPI theo kiến trúc modular
monolith. Backend hỗ trợ identity theo organization, RBAC, vòng đời tài liệu,
AI runs bất đồng bộ, Server-Sent Events, worker, và AI gateway độc lập nhà cung
cấp với chế độ fallback deterministic cho local/test.

## Công nghệ sử dụng

| Phần | Công nghệ |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Radix UI |
| Backend | Python 3.14, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic |
| Dữ liệu | SQLite cho demo/test local, PostgreSQL cho deployment |
| Worker | Local workflow dispatcher khi phát triển, Celery/Redis cho distributed worker |
| AI |Gemini, OpenRouter và offline provider deterministic |
| Kiểm thử | Pytest, Ruff, Mypy, architecture tests, contract tests, frontend typecheck/build |

## Chạy nhanh ở local

```bash
make install-local
make dev-all
```

Sau khi chạy:

- Frontend: http://localhost:3000
- Backend API: http://127.0.0.1:8000/api/v1
- API reference: http://127.0.0.1:8000/scalar

Swagger UI của FastAPI tại `/docs` được tắt có chủ đích. Dự án dùng Scalar tại
`/scalar` để xem tài liệu API.

## Lệnh thường dùng

```bash
make env                # tạo file môi trường local nếu chưa có
make install-local      # cài dependency cho backend và frontend
make backend-init-db    # tạo schema và seed dữ liệu demo
make dev-all            # chạy backend và frontend ở background
make dev-foreground     # chạy backend và frontend ở foreground
make dev-logs           # xem log local
make dev-down           # dừng các process local
make check              # chạy backend tests và frontend typecheck/build
```

## Cấu trúc thư mục

```text
C2-App-037/
├── backend/            # FastAPI API, modules, workers, migrations, tests
├── frontend/           # Next.js app, BFF routes, shared UI, generated API types
├── eval/               # ghi chú và bằng chứng evaluation
├── scripts/            # script hỗ trợ phát triển/khóa học
├── streamlit_flows/    # thử nghiệm workflow bằng Streamlit
├── tests/              # test và integration check ở root
├── docs/archive/       # tài liệu dài đã lưu trữ
├── Makefile            # lệnh phát triển ở root
└── README.md
```

## Kiến trúc backend

Backend dùng kiểu modular monolith bốn lớp. Mỗi business module thường được
tách theo HTTP contract, use case, domain rule và infrastructure adapter:

```text
module/
├── api/
├── application/
├── domain/
└── infrastructure/
```

`backend/app/bootstrap/routes.py` là HTTP composition root. Domain code được giữ
độc lập với FastAPI, SQLAlchemy và platform adapter; các architecture tests kiểm
tra các ranh giới này.

## Tài liệu liên quan

- Tổng quan backend: `backend/README.md`
- Bằng chứng evaluation: `eval/README.md`
- README dài đã lưu trữ: `docs/archive/README-legacy-full.md`
- API docs: chạy backend rồi mở http://127.0.0.1:8000/scalar

## Môi trường

Tạo file môi trường local bằng:

```bash
make env
```

Các file `.env`, `backend/.env` và `frontend/.env.local` không được commit. Khi
cấu hình máy mới hoặc deployment mới, dùng các file `.env.example` làm điểm bắt
đầu.
