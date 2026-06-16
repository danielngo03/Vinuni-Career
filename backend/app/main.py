from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import get_scalar_api_reference

from app.api.compat import router as compat_router
from app.api.exceptions import register_exception_handlers
from app.api.middlewares.context import RequestContextMiddleware
from app.api.middlewares.rate_limit import InMemoryRateLimitMiddleware
from app.api.router import api_router
from app.core.config import settings
from app.core.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(InMemoryRateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.backend_cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(compat_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    if settings.scalar_docs_enabled:

        @app.get(settings.scalar_docs_path, include_in_schema=False)
        async def scalar_html():
            return get_scalar_api_reference(
                openapi_url=app.openapi_url,
                title=f"{settings.app_name} API Reference",
            )

    return app


app = create_app()
