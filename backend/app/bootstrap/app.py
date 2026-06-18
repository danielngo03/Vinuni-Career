"""
Bootstrap — FastAPI application factory.

The create_app() factory is the single entry point for app creation.
It wires middleware, exception handlers, and routers in the correct order.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import get_scalar_api_reference

from app.bootstrap.exceptions import register_exception_handlers
from app.bootstrap.lifespan import lifespan
from app.bootstrap.middleware.context import RequestContextMiddleware
from app.bootstrap.middleware.rate_limit import DistributedRateLimitMiddleware
from app.bootstrap.routes import build_router
from app.shared.config import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        version="2.0.0",
        description="VinUni Career Platform — V2 Modular API",
        docs_url=None,         # Disabled in favour of Scalar
        redoc_url=None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters — applied bottom-up) ──────────────────
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(DistributedRateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(o) for o in settings.backend_cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ──────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Routers ────────────────────────────────────────────────────────
    app.include_router(build_router(), prefix=settings.api_v1_prefix)

    # ── API Docs (Scalar) ───────────────────────────────────────────────
    if settings.scalar_docs_enabled:
        @app.get(settings.scalar_docs_path, include_in_schema=False)
        async def scalar_html():
            return get_scalar_api_reference(
                openapi_url=app.openapi_url,
                title=f"{settings.app_name} API Reference",
            )

    return app
