"""Central model registry.

Importing this module imports every ORM model module so they register on
``Base.metadata``. Used by Alembic autogenerate/target metadata and by tests that
create the schema with ``Base.metadata.create_all``.
"""

from __future__ import annotations

from app.ai.agents import models as _ai_workforce_models  # noqa: F401
from app.ai.gateway import provider_models as _ai_provider_models  # noqa: F401
from app.ai.observability import eval_samples as _ai_eval_samples  # noqa: F401
from app.ai.observability import models as _ai_usage_models  # noqa: F401
from app.modules.advertising.domain import models as _advertising_models  # noqa: F401
from app.modules.ai_assistant.domain import models as _ai_assistant_models  # noqa: F401
from app.modules.ai_settings.domain import models as _ai_settings_models  # noqa: F401
from app.modules.ai_settings.domain import (  # noqa: F401
    routing_models as _ai_routing_models,
)
from app.modules.analytics.domain import models as _analytics_models  # noqa: F401
from app.modules.analytics.domain import (  # noqa: F401
    partner_read_models as _partner_analytics_models,
)
from app.modules.auth.domain import models as _auth_models  # noqa: F401
from app.modules.automation.scheduler import models as _scheduler_run_models  # noqa: F401
from app.modules.billing.domain import models as _billing_models  # noqa: F401
from app.modules.career_outcomes.domain import (  # noqa: F401
    models as _career_outcome_models,
)
from app.modules.career_services.domain import (  # noqa: F401
    models as _career_services_models,
)
from app.modules.compliance.domain import models as _compliance_models  # noqa: F401
from app.modules.dashboards.domain import models as _dashboards_models  # noqa: F401
from app.modules.discovery.domain import models as _discovery_models  # noqa: F401
from app.modules.discovery.domain import search_log_model as _search_log_model  # noqa: F401
from app.modules.documents.domain import models as _documents_models  # noqa: F401
from app.modules.knowledge_base.domain import models as _knowledge_base_models  # noqa: F401
from app.modules.messaging.domain import models as _messaging_models  # noqa: F401
from app.modules.mock_interview.domain import models as _mock_interview_models  # noqa: F401
from app.modules.moderation.domain import models as _moderation_models  # noqa: F401
from app.modules.notifications.domain import models as _notification_models  # noqa: F401
from app.modules.onboarding.domain import models as _onboarding_models  # noqa: F401
from app.modules.opportunities.domain import (  # noqa: F401
    event_models as _event_models,
)
from app.modules.opportunities.domain import (  # noqa: F401
    industry_models as _industry_models,
)
from app.modules.opportunities.domain import models as _opportunity_models  # noqa: F401
from app.modules.organization.domain import models as _org_models  # noqa: F401
from app.modules.platform_admin.domain import models as _platform_admin_models  # noqa: F401
from app.modules.platform_feedback.domain import models as _platform_feedback_models  # noqa: F401
from app.modules.recruitment.domain import models as _recruitment_models  # noqa: F401
from app.modules.reviews.domain import models as _reviews_models  # noqa: F401
from app.modules.student_profiles.domain import (  # noqa: F401
    models as _student_profile_models,
)
from app.modules.talent_pool.domain import models as _talent_pool_models  # noqa: F401
from app.modules.users.domain import models as _user_models  # noqa: F401
from app.modules.workflow.domain import models as _workflow_models  # noqa: F401

# Importing for side effects registers tables on Base.metadata.
from app.shared import models as _shared_models  # noqa: F401
from app.shared.models import Base  # noqa: F401  (re-exported)

target_metadata = Base.metadata


def import_all_models() -> None:
    """No-op accessor that guarantees model modules are imported."""

    _ = (
        _shared_models,
        _ai_provider_models,
        _ai_usage_models,
        _ai_eval_samples,
        _ai_workforce_models,
        _advertising_models,
        _scheduler_run_models,
        _ai_assistant_models,
        _analytics_models,
        _partner_analytics_models,
        _ai_settings_models,
        _ai_routing_models,
        _discovery_models,
        _search_log_model,
        _billing_models,
        _notification_models,
        _user_models,
        _auth_models,
        _org_models,
        _opportunity_models,
        _event_models,
        _industry_models,
        _documents_models,
        _recruitment_models,
        _messaging_models,
        _mock_interview_models,
        _moderation_models,
        _student_profile_models,
        _talent_pool_models,
        _career_outcome_models,
        _career_services_models,
        _compliance_models,
        _dashboards_models,
        _reviews_models,
        _knowledge_base_models,
        _platform_admin_models,
        _platform_feedback_models,
        _workflow_models,
        _onboarding_models,
    )
