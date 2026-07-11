"""Shared helpers for auth/account tests (service-level)."""

from __future__ import annotations

from app.modules.auth.application import auth_service
from app.modules.auth.application.context import RequestContext
from app.modules.notifications.domain.models import NotificationOutbox
from app.modules.users.application import user_service
from app.modules.users.domain.models import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

CTX = RequestContext(ip="203.0.113.7", user_agent="Mozilla/5.0 (Macintosh) Chrome/120")


async def fetch_verification_token(session: AsyncSession, user_id) -> str:
    rows = (
        (
            await session.execute(
                select(NotificationOutbox)
                .where(NotificationOutbox.recipient_id == user_id)
                .order_by(NotificationOutbox.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if row.template_key == "account.email_verification":
            return str(row.variables["token"])
    raise AssertionError("no verification token enqueued")


async def register_verified(
    session: AsyncSession,
    *,
    email: str,
    password: str = "Sup3rSecret!",
    full_name: str = "Test User",
    locale: str = "vi",
) -> User:
    await auth_service.register(
        session,
        email=email,
        password=password,
        full_name=full_name,
        locale=locale,
        ctx=CTX,
    )
    user = await user_service.get_by_email(session, email)
    assert user is not None
    token = await fetch_verification_token(session, user.id)
    await auth_service.verify_email(session, token=token, ctx=CTX)
    refreshed = await user_service.get_by_email(session, email)
    assert refreshed is not None
    return refreshed
