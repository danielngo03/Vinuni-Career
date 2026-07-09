"""Account + notification preference read/write.

Merges stored ``user_preferences`` / ``notification_preferences`` with the default
category catalogue. Mandatory categories (security/compliance/lifecycle/billing)
are always returned ``locked`` and cannot be disabled by a PATCH
(``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §5).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.domain.models import NotificationPreference, UserPreference
from app.modules.users.domain.preferences import (
    DEFAULT_CATEGORIES,
    EMAIL_SETTINGS,
    is_mandatory,
)
from app.shared.exceptions import ValidationFailedError


async def _get_or_create_user_preference(
    session: AsyncSession, user_id: uuid.UUID
) -> UserPreference:
    pref = (
        await session.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    ).scalar_one_or_none()
    if pref is None:
        pref = UserPreference(user_id=user_id)
        session.add(pref)
        await session.flush()
    return pref


async def _category_map(
    session: AsyncSession, user_id: uuid.UUID
) -> dict[str, NotificationPreference]:
    rows = (
        (
            await session.execute(
                select(NotificationPreference).where(NotificationPreference.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    return {row.category: row for row in rows}


async def get_preferences(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Any]:
    pref = await _get_or_create_user_preference(session, user_id)
    stored = await _category_map(session, user_id)

    categories: dict[str, Any] = {}
    for default in DEFAULT_CATEGORIES:
        locked = is_mandatory(default.category)
        row = stored.get(default.category)
        if locked:
            categories[default.category] = {
                "in_app": True,
                "email": "mandatory",
                "push": row.push_enabled if row else default.push,
                "locked": True,
            }
        elif row is not None:
            categories[default.category] = {
                "in_app": row.in_app_enabled,
                "email": row.email_setting,
                "push": row.push_enabled,
                "locked": False,
            }
        else:
            categories[default.category] = {
                "in_app": default.in_app,
                "email": default.email,
                "push": default.push,
                "locked": False,
            }

    return {
        "locale": pref.locale,
        "timezone": pref.timezone,
        "theme": pref.theme,
        "quiet_hours": pref.quiet_hours or {},
        "categories": categories,
    }


async def patch_preferences(
    session: AsyncSession, user_id: uuid.UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    pref = await _get_or_create_user_preference(session, user_id)

    if "locale" in payload and payload["locale"] is not None:
        if payload["locale"] not in {"vi", "en"}:
            raise ValidationFailedError(details={"field": "locale"})
        pref.locale = payload["locale"]
    if "timezone" in payload and payload["timezone"] is not None:
        pref.timezone = str(payload["timezone"])[:100]
    if "theme" in payload and payload["theme"] is not None:
        if payload["theme"] not in {"system", "light", "dark"}:
            raise ValidationFailedError(details={"field": "theme"})
        pref.theme = payload["theme"]
    if "quiet_hours" in payload and payload["quiet_hours"] is not None:
        if not isinstance(payload["quiet_hours"], dict):
            raise ValidationFailedError(details={"field": "quiet_hours"})
        pref.quiet_hours = payload["quiet_hours"]

    categories = payload.get("categories") or {}
    if not isinstance(categories, dict):
        raise ValidationFailedError(details={"field": "categories"})

    stored = await _category_map(session, user_id)
    for category, settings in categories.items():
        if not isinstance(settings, dict):
            raise ValidationFailedError(details={"field": f"categories.{category}"})
        if is_mandatory(category):
            # Mandatory categories cannot be disabled; ignore in_app/email changes.
            row = stored.get(category)
            if "push" in settings:
                if row is None:
                    row = NotificationPreference(
                        user_id=user_id,
                        category=category,
                        in_app_enabled=True,
                        email_setting="mandatory",
                    )
                    session.add(row)
                row.push_enabled = bool(settings["push"])
            continue

        email_setting = settings.get("email")
        if isinstance(email_setting, bool):
            email_setting = "immediate" if email_setting else "off"
        if email_setting is not None and email_setting not in EMAIL_SETTINGS:
            raise ValidationFailedError(details={"field": f"categories.{category}.email"})

        row = stored.get(category)
        if row is None:
            row = NotificationPreference(user_id=user_id, category=category)
            session.add(row)
            stored[category] = row
        if "in_app" in settings:
            row.in_app_enabled = bool(settings["in_app"])
        if email_setting is not None:
            row.email_setting = email_setting
        if "push" in settings:
            row.push_enabled = bool(settings["push"])

    await session.flush()
    return await get_preferences(session, user_id)
