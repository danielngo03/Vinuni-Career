"""Default notification templates and an idempotent seeder.

The outbox worker (:func:`process_outbox`) renders an *active* template for each
queued row; a missing template fails the row with ``TEMPLATE_NOT_FOUND``. The auth
foundation enqueues three account emails — ``account.email_verification``,
``account.password_reset``, ``account.password_changed`` — so a baseline set of
``active`` ``email`` templates (vi + en) must exist out of the box.

University admins can later author their own versions through the template builder
(``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §4); this seed only fills gaps and
never overwrites an existing template for the same ``(key, channel, locale)``.

``ensure_default_templates`` is idempotent and safe to run repeatedly (startup hook
and ``scripts/seed_notification_templates.py``). Each seeded template is validated
with :func:`validate_template` so its declared ``variables_schema`` matches the
variables actually used in the body/subject.

The seed copy itself (subject/body strings per key/locale) lives in
``template_seed_data.DEFAULT_TEMPLATES`` — re-exported here so existing callers
that import ``DEFAULT_TEMPLATES`` from this module keep working unchanged.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.application.template_renderer import validate_template
from app.modules.notifications.application.template_seed_data import DEFAULT_TEMPLATES
from app.modules.notifications.domain.models import NotificationTemplate

__all__ = ["DEFAULT_TEMPLATES", "ensure_default_templates"]


async def ensure_default_templates(session: AsyncSession) -> int:
    """Insert any missing default templates as ``active``. Returns rows created.

    Idempotent: an existing template for the same ``(key, channel, locale)`` is
    left untouched (including admin-authored overrides). Does not commit — the
    caller owns the transaction.
    """

    created = 0
    for spec in DEFAULT_TEMPLATES:
        key = spec["key"]
        channel = spec["channel"]
        schema = spec["variables_schema"]
        for locale, content in spec["locales"].items():
            exists = (
                await session.execute(
                    select(NotificationTemplate.id).where(
                        NotificationTemplate.key == key,
                        NotificationTemplate.channel == channel,
                        NotificationTemplate.locale == locale,
                    )
                )
            ).first()
            if exists is not None:
                continue

            # Fail loudly at seed time if a default template is malformed.
            validate_template(
                body=content["body"],
                subject=content.get("subject"),
                title=content.get("title"),
                variables_schema=schema,
            )
            session.add(
                NotificationTemplate(
                    owner_scope="university",
                    owner_org_id=None,
                    key=key,
                    channel=channel,
                    locale=locale,
                    version=1,
                    status="active",
                    subject=content.get("subject"),
                    title=content.get("title"),
                    body=content["body"],
                    variables_schema=schema,
                )
            )
            created += 1

    if created:
        await session.flush()
    return created
