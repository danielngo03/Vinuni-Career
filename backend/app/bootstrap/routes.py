"""Single composition root for HTTP routes."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter

from app.bootstrap import health
from app.modules.access.api.router import router as auth_router
from app.modules.ai_operations.api import legacy
from app.modules.ai_operations.api.router import router as ai_runs_router
from app.modules.automation.api import webhooks, workflows
from app.modules.documents.api import legacy_files
from app.modules.documents.api import router as documents_router
from app.modules.engagement.api import notifications, reviews
from app.modules.institution.api.router import router as institution_router
from app.modules.opportunities.api import events, jobs
from app.modules.platform.api import search
from app.modules.recruitment.api import applications, cvs, interviews
from app.modules.registrations.router import router as registration_router
from app.modules.reporting.api import dashboard
from app.modules.students.api.router import router as students_router


@dataclass(frozen=True)
class RouteRegistration:
    router: APIRouter
    prefix: str = ""
    tags: tuple[str, ...] = ()
    include_in_schema: bool = True


ROUTES = (
    RouteRegistration(health.router, tags=("health",)),
    RouteRegistration(auth_router, "/auth", ("access",)),
    RouteRegistration(students_router, "/students", ("students",)),
    RouteRegistration(institution_router, "/organizations", ("institution",)),
    RouteRegistration(registration_router, "/registrations", ("verification",)),
    RouteRegistration(documents_router, tags=("documents",)),
    RouteRegistration(ai_runs_router, tags=("ai-runs",)),
    RouteRegistration(jobs.router, "/jobs", ("opportunities",)),
    RouteRegistration(events.router, "/events", ("opportunities",)),
    RouteRegistration(applications.router, "/jobs", ("recruitment",)),
    RouteRegistration(cvs.router, "/cvs", ("recruitment",)),
    RouteRegistration(interviews.router, "/interviews", ("recruitment",)),
    RouteRegistration(dashboard.router, "/dashboard", ("reporting",)),
    RouteRegistration(reviews.router, "/reviews", ("engagement",)),
    RouteRegistration(notifications.router, "/notifications", ("engagement",)),
    # Compatibility routes remain explicit and measurable.
    RouteRegistration(legacy.router, "/ai", ("compatibility/ai",)),
    RouteRegistration(
        institution_router,
        "/orgs",
        ("compatibility/organizations",),
        include_in_schema=False,
    ),
    RouteRegistration(workflows.router, "/workflows", ("automation",)),
    RouteRegistration(webhooks.router, "/webhooks", ("automation",)),
    RouteRegistration(legacy_files.router, "/files", ("compatibility/files",)),
    RouteRegistration(search.router, "/search", ("search",)),
)


def build_router() -> APIRouter:
    """Build a fresh root router from the declarative registry."""
    api_router = APIRouter()
    for registration in ROUTES:
        api_router.include_router(
            registration.router,
            prefix=registration.prefix,
            tags=list(registration.tags),
            include_in_schema=registration.include_in_schema,
        )
    return api_router
