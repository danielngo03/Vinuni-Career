"""Mount all module routers under ``/api/v1``."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app.ai.agents.api import router as ai_workforce_router
from app.api import health
from app.modules.account.api import router as account_router
from app.modules.advertising.api import router as advertising_router
from app.modules.ai_assistant.api.router import router as ai_assistant_router
from app.modules.ai_assistant.api.router import usage_router as ai_usage_router
from app.modules.ai_governance.api.router import (
    admin_allocation_router as ai_governance_admin_allocation_router,
)
from app.modules.ai_governance.api.router import (
    admin_capacity_router as ai_governance_admin_capacity_router,
)
from app.modules.ai_governance.api.router import (
    university_capacity_router as ai_governance_university_capacity_router,
)
from app.modules.ai_ops.api import router as ai_ops_router
from app.modules.ai_settings.api import router as ai_settings_router
from app.modules.analytics.api.partner_router import router as analytics_partner_router
from app.modules.auth.api import router as auth_router
from app.modules.billing.api import router as billing_router
from app.modules.career_outcomes.api import router as career_outcomes_router
from app.modules.career_services.api import router as career_services_router
from app.modules.compliance.api import router as compliance_router
from app.modules.dashboards.api import router as dashboards_router
from app.modules.dashboards.api.admin_router import admin_router as dashboards_admin_router
from app.modules.discovery.api import recommendations_router as discovery_reco
from app.modules.discovery.api import router as discovery_router
from app.modules.discovery.api.search_router import router as search_router
from app.modules.documents.api import router as documents_router
from app.modules.knowledge_base.api.router import router as knowledge_base_router
from app.modules.locations.api.router import router as locations_router
from app.modules.marketplace.api import router as marketplace_router
from app.modules.messaging.api import router as messaging_router
from app.modules.moderation.api.router import content_reports_router
from app.modules.moderation.api.router import router as moderation_router
from app.modules.notifications.api import router as notifications_router
from app.modules.onboarding.api import router as onboarding_router
from app.modules.opportunities.api import router as opportunities_router
from app.modules.opportunities.api.events_router import (
    admin_events_router,
    events_router,
)
from app.modules.organization.api import router as organization_router
from app.modules.organization.api.public_router import companies_router
from app.modules.platform_admin.api.router import admin_router as platform_admin_audit_router
from app.modules.platform_admin.api.router import (
    alerts_incidents_router as platform_admin_alerts_incidents_router,
)
from app.modules.platform_admin.api.router import (
    alerts_rules_router as platform_admin_alerts_rules_router,
)
from app.modules.platform_admin.api.router import (
    analytics_router as platform_admin_analytics_router,
)
from app.modules.platform_admin.api.router import catalog_router as platform_admin_catalog_router
from app.modules.platform_admin.api.router import flags_router as platform_admin_flags_router
from app.modules.platform_admin.api.router import health_router as platform_admin_health_router
from app.modules.platform_admin.api.router import sessions_router as platform_admin_sessions_router
from app.modules.platform_admin.api.router import users_router as platform_admin_users_router
from app.modules.platform_feedback.api.router import router as platform_feedback_router
from app.modules.platform_settings.api import router as platform_settings_router
from app.modules.platform_support.api import router as platform_support_router
from app.modules.recruitment.api import router as recruitment_router
from app.modules.reviews.api import router as reviews_router
from app.modules.student_profiles.api import router as student_profiles_router
from app.modules.users.api import router as admin_users_router
from app.modules.workflow.api import router as workflow_router

API_PREFIX = "/api/v1"


def register_routes(app: FastAPI) -> None:
    api = APIRouter(prefix=API_PREFIX)
    api.include_router(health.router)
    api.include_router(auth_router.router)
    api.include_router(onboarding_router.router)
    api.include_router(account_router.router)
    api.include_router(organization_router.router)
    api.include_router(companies_router)
    api.include_router(marketplace_router.router)
    api.include_router(discovery_router.router)
    api.include_router(search_router)
    # Static recommendation/similar paths under /jobs MUST be registered before the
    # opportunities router so `/jobs/recommendations` is not captured by
    # `/jobs/{job_id}` (enumeration-safe static-path precedence).
    api.include_router(discovery_reco.jobs_reco_router)
    api.include_router(discovery_reco.admin_discovery_router)
    api.include_router(opportunities_router.router)
    # Events: static sub-paths (/mine, /registrations/mine) MUST precede the
    # parameterised /{event_id} route to avoid path capture.
    api.include_router(events_router)
    api.include_router(admin_events_router)
    api.include_router(documents_router.router)
    api.include_router(recruitment_router.router)
    api.include_router(reviews_router.router)
    api.include_router(reviews_router.admin_router)
    api.include_router(student_profiles_router.router)
    api.include_router(dashboards_router.router)
    api.include_router(dashboards_admin_router)
    api.include_router(career_outcomes_router.router)
    api.include_router(career_services_router)
    api.include_router(compliance_router.router)
    api.include_router(compliance_router.admin_router)
    api.include_router(notifications_router.router)
    api.include_router(notifications_router.template_admin_router)
    api.include_router(messaging_router.router)
    api.include_router(moderation_router)
    api.include_router(content_reports_router)
    api.include_router(platform_support_router.router)
    api.include_router(advertising_router.router)
    api.include_router(advertising_router.admin_router)
    api.include_router(analytics_partner_router)
    api.include_router(billing_router.router)
    api.include_router(billing_router.admin_router)
    api.include_router(ai_assistant_router)
    api.include_router(ai_usage_router)
    api.include_router(ai_governance_university_capacity_router)
    api.include_router(ai_governance_admin_capacity_router)
    api.include_router(ai_governance_admin_allocation_router)
    api.include_router(ai_workforce_router)
    api.include_router(ai_settings_router.admin_router)
    api.include_router(ai_ops_router.admin_router)
    api.include_router(platform_admin_audit_router)
    api.include_router(platform_admin_health_router)
    api.include_router(platform_admin_users_router)
    api.include_router(platform_admin_sessions_router)
    api.include_router(platform_admin_analytics_router)
    api.include_router(platform_admin_flags_router)
    api.include_router(platform_admin_catalog_router)
    api.include_router(platform_admin_alerts_rules_router)
    api.include_router(platform_admin_alerts_incidents_router)
    api.include_router(platform_settings_router.public_router)
    api.include_router(platform_settings_router.admin_router)
    api.include_router(locations_router)
    api.include_router(admin_users_router.router)
    api.include_router(knowledge_base_router)
    api.include_router(platform_feedback_router)
    api.include_router(workflow_router.router)
    app.include_router(api)
