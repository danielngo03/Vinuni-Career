"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import Theme, get_scalar_api_reference

from app.bootstrap.errors import register_exception_handlers
from app.bootstrap.lifespan import lifespan
from app.bootstrap.middleware import RequestIdMiddleware
from app.bootstrap.routes import register_routes
from app.core.config import get_settings
from app.core.logging import configure_logging

_DESCRIPTION = """
## VinUni Career Platform — REST API v1

Nền tảng tuyển dụng của Đại học VinUni kết nối sinh viên, nhà tuyển dụng và
bộ phận quan hệ doanh nghiệp của trường.

### Xác thực
Tất cả các endpoint được bảo vệ yêu cầu Bearer JWT trong header `Authorization`.
Token được cấp qua `/api/v1/auth/login` (refresh cookie httpOnly).

### Phân quyền
`student` · `partner_admin` · `partner_member` · `university_staff` · `superadmin`

### Phiên bản API
Tất cả các endpoint dùng prefix `/api/v1`. Các thay đổi breaking sẽ
nâng lên `/api/v2`.

### Liên kết nhanh
- **Scalar UI** `/api/scalar` — giao diện đẹp, thân thiện hơn Swagger
- **OpenAPI JSON** `/api/openapi.json`
- **Health** `/api/v1/health`
"""

_TAGS_METADATA = [
    {"name": "auth", "description": "Đăng nhập, đăng ký, làm mới token, TOTP 2FA, OAuth"},
    {"name": "account", "description": "Thông tin tài khoản, thiết bị, đặt lại mật khẩu"},
    {"name": "organizations", "description": "Tổ chức (đối tác/trường), thành viên, RBAC"},
    {"name": "opportunities", "description": "Tin tuyển dụng (CRUD, duyệt, embed AI)"},
    {"name": "events", "description": "Sự kiện tuyển dụng, đăng ký, check-in"},
    {"name": "recruitment", "description": "Ứng tuyển, pipeline, phỏng vấn, scorecard, offer"},
    {"name": "documents", "description": "CV upload, CV Studio, xuất PDF, job-fit AI"},
    {"name": "discovery", "description": "Tìm kiếm toàn văn, gợi ý việc làm, session khách"},
    {"name": "marketplace", "description": "Trang công khai: jobs, events, companies"},
    {"name": "student_profiles", "description": "Hồ sơ sinh viên, kỹ năng, học vấn, kinh nghiệm"},
    {"name": "ai_assistant", "description": "Chat AI, công cụ trợ lý, lịch sử phiên"},
    {"name": "ai_settings", "description": "Admin AI: provider, model alias, budget, trạng thái"},
    {"name": "knowledge_base", "description": "Upload tài liệu, RAG retrieval (KB)"},
    {"name": "messaging", "description": "Tin nhắn nội bộ tổ chức (không peer-to-peer)"},
    {"name": "notifications", "description": "Thông báo in-app, email, tuỳ chỉnh thiết bị"},
    {"name": "advertising", "description": "Vị trí quảng cáo có tài trợ, duyệt creative"},
    {"name": "billing", "description": "Gói đăng ký, thanh toán thủ công/ngân hàng"},
    {"name": "reviews", "description": "Đánh giá công ty, vote hữu ích"},
    {"name": "career_outcomes", "description": "Kết quả việc làm của sinh viên tốt nghiệp"},
    {
        "name": "career-services",
        "description": "Không gian làm việc chuyên viên hướng nghiệp: nhóm sinh viên, "
        "sinh viên có rủi ro, hàng đợi duyệt CV, lịch hẹn, ghi chú nhà tuyển dụng",
    },
    {"name": "dashboards", "description": "Dashboard tổng hợp theo persona"},
    {"name": "platform_settings", "description": "Admin: cài đặt nền tảng toàn cục"},
    {"name": "locations", "description": "Tỉnh/thành, quận/huyện (Việt Nam)"},
    {"name": "health", "description": "Health-check và readiness probe"},
]


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="VinUni Career Platform API",
        version="1.0.0",
        description=_DESCRIPTION,
        openapi_tags=_TAGS_METADATA,
        contact={
            "name": "VinUni Career Center",
            "email": "careers@vinuni.edu.vn",
        },
        license_info={
            "name": "Private — VinUni Internal Use Only",
        },
        # Disable default Swagger UI — Scalar is used instead (mounted below)
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)
    register_routes(app)
    _mount_scalar(app)
    return app


def _mount_scalar(app: FastAPI) -> None:
    """Mount Scalar API reference UI at /api/scalar.

    Scalar provides a modern, developer-friendly alternative to Swagger UI with
    better readability, dark mode, code samples in many languages, and search.
    Available at http://localhost:8000/api/scalar after server start.
    """

    @app.get("/api/scalar", include_in_schema=False)
    async def scalar_html():
        return get_scalar_api_reference(
            openapi_url="/api/openapi.json",
            title="VinUni Career Platform — API Reference",
            theme=Theme.PURPLE,
        )


app = create_app()
